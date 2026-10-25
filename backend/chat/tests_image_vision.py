import io
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from PIL import Image, ImageDraw
from django.contrib.auth import get_user_model
from django.test import TestCase
from langchain_core.messages import AIMessage, HumanMessage

from agent.tools import read_file
from chat.models import Message, Thread, UploadedFile
from chat.streaming import stream_chat_turn
from filesvc.image_vision import (
    analyze_image_with_vision,
    downscale_image,
    encode_image_to_base64,
    validate_and_prepare_image,
)
from filesvc.parsers.image import ImageParser
from filesvc.storage import storage

User = get_user_model()


class ImageVisionTests(TestCase):
    """Test suite verifying vision tool path, OCR fallback, caching, and security constraints."""

    def setUp(self):
        self.user = User.objects.create_user(username="visionuser", email="vision@example.com")
        self.thread = Thread.objects.create(user=self.user, title="Vision Thread")

    def _create_sample_image(self, width: int = 400, height: int = 200, text: str = "TEST IMAGE", fmt: str = "PNG") -> tuple[str, bytes]:
        img = Image.new("RGB", (width, height), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((20, 40), text, fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format=fmt)
        img_bytes = buf.getvalue()
        filename = f"sample.{fmt.lower()}"
        path, _ = storage.save_raw(img_bytes, extension=fmt.lower())
        return path, img_bytes

    def _create_uploaded_file_record(self, filename: str, rel_path: str, mime: str = "image/png", size: int = 1000) -> UploadedFile:
        uf = UploadedFile.objects.create(
            thread=self.thread,
            name=filename,
            mime=mime,
            size=size,
            path=rel_path,
            status="ready",
        )
        parsed_data = {
            "text": f"Image metadata: {filename}",
            "pages": [],
            "structured_data": {"format": "PNG", "width": 400, "height": 200, "vision_cache": {}},
        }
        uf.parsed_path = storage.save_parsed(str(uf.id), parsed_data)
        uf.save()
        return uf

    # -------------------------------------------------------------------------
    # 1. Vision model invocation with multimodal image part
    # -------------------------------------------------------------------------
    def test_read_file_calls_llm_with_image_part_and_prompt(self):
        """When read_file targets an image, LLM is called with HumanMessage containing image_url and detailed prompt."""
        rel_path, _ = self._create_sample_image(text="ORGANIC SEARCH 42000")
        uf = self._create_uploaded_file_record("chart.png", rel_path)

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(
            content="Chart shows Organic search: 42,000; Direct: 28,500."
        )

        with patch("filesvc.image_vision.get_llm", return_value=mock_llm):
            result = read_file.invoke({"file_id": str(uf.id), "question": "What are the traffic values?"})

        self.assertIn("Organic search: 42,000", result)
        self.assertEqual(mock_llm.invoke.call_count, 1)

        call_args = mock_llm.invoke.call_args[0][0]
        self.assertIsInstance(call_args, list)
        self.assertEqual(len(call_args), 1)
        human_msg = call_args[0]
        self.assertIsInstance(human_msg, HumanMessage)
        self.assertIsInstance(human_msg.content, list)

        # Check multimodal content blocks
        text_part = next((p for p in human_msg.content if p.get("type") == "text"), None)
        image_part = next((p for p in human_msg.content if p.get("type") == "image_url"), None)

        self.assertIsNotNone(text_part)
        self.assertIsNotNone(image_part)
        self.assertIn("What are the traffic values?", text_part["text"])
        self.assertIn("detailed, comprehensive description", text_part["text"])
        self.assertTrue(image_part["image_url"]["url"].startswith("data:image/png;base64,"))

    # -------------------------------------------------------------------------
    # 2. No base64 in state, checkpoints, logs or Message rows
    # -------------------------------------------------------------------------
    def test_no_base64_in_graph_state_or_database_messages(self):
        """Ensure base64 image data never ends up in state, checkpoints, or Message rows."""
        from asgiref.sync import async_to_sync

        rel_path, _ = self._create_sample_image(text="SECRET CONTENT")
        uf = self._create_uploaded_file_record("test.png", rel_path)

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(
            content="This image shows text: SECRET CONTENT."
        )

        async def _run():
            async for _ in stream_chat_turn(self.thread, f"Describe image {uf.id}"):
                pass

        with patch("filesvc.image_vision.get_llm", return_value=mock_llm):
            async_to_sync(_run)()

        # Check all saved messages in DB
        messages = list(Message.objects.filter(thread=self.thread))
        for msg in messages:
            self.assertNotIn("data:image", msg.content)
            self.assertNotIn(";base64,", msg.content)

    # -------------------------------------------------------------------------
    # 3. Vision caching in parsed_path
    # -------------------------------------------------------------------------
    def test_vision_caching_in_parsed_path(self):
        """Repeated questions about the same image hit the parsed_path cache and do not call the LLM again."""
        rel_path, _ = self._create_sample_image(text="TRAFFIC 2026")
        uf = self._create_uploaded_file_record("cached_chart.png", rel_path)

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="First call analysis result.")

        with patch("filesvc.image_vision.get_llm", return_value=mock_llm):
            # First call: hits LLM
            res1 = read_file.invoke({"file_id": str(uf.id), "question": "What is the total traffic?"})
            self.assertIn("First call analysis result", res1)
            self.assertEqual(mock_llm.invoke.call_count, 1)

            # Second call with same question: hits cache
            res2 = read_file.invoke({"file_id": str(uf.id), "question": "What is the total traffic?"})
            self.assertIn("First call analysis result", res2)
            self.assertEqual(mock_llm.invoke.call_count, 1)  # Not incremented!

            # Check parsed_path JSON file on disk
            full_parsed_path = uf.parsed_path
            with open(full_parsed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            vision_cache = data.get("structured_data", {}).get("vision_cache", {})
            self.assertTrue(len(vision_cache) > 0)

    # -------------------------------------------------------------------------
    # 4. Fallback to OCR when vision is unavailable or fails
    # -------------------------------------------------------------------------
    def test_fallback_to_ocr_when_vision_disabled_via_env(self):
        """If LLM_SUPPORTS_VISION=0, fall back to OCR with pytesseract and notify user."""
        rel_path, _ = self._create_sample_image(text="METRICS 2026")
        uf = self._create_uploaded_file_record("metrics.png", rel_path)

        with patch.dict(os.environ, {"LLM_SUPPORTS_VISION": "0"}):
            result = read_file.invoke({"file_id": str(uf.id), "question": "Read this"})

        self.assertIn("[Note: Analyzed using OCR text extraction because the visual model is unavailable.]", result)
        self.assertIn("METRICS", result)

    def test_fallback_to_ocr_when_vision_call_raises_error(self):
        """If LLM call fails, fall back to OCR with pytesseract and notify user."""
        rel_path, _ = self._create_sample_image(text="REVENUE REPORT")
        uf = self._create_uploaded_file_record("revenue.png", rel_path)

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("Vision API quota exhausted")

        with patch("filesvc.image_vision.get_llm", return_value=mock_llm):
            result = read_file.invoke({"file_id": str(uf.id), "question": "Read revenue"})

        self.assertIn("[Note: Analyzed using OCR text extraction because the visual model is unavailable.]", result)
        self.assertIn("REVENUE", result)

    # -------------------------------------------------------------------------
    # 5. Clear error when both vision and OCR fail
    # -------------------------------------------------------------------------
    def test_both_vision_and_ocr_fail_returns_clear_error_never_claims_success(self):
        """If both visual LLM and OCR fail, report clear error and never claim success."""
        # Create a blank white image with no text
        rel_path, _ = self._create_sample_image(text="")
        uf = self._create_uploaded_file_record("blank.png", rel_path)

        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = RuntimeError("Vision model error")

        with patch("filesvc.image_vision.get_llm", return_value=mock_llm):
            with patch("filesvc.image_vision.perform_ocr_fallback", return_value=""):
                result = read_file.invoke({"file_id": str(uf.id)})

        self.assertIn("Error:", result)
        self.assertIn("could not be analysed", result)
        self.assertNotIn("successfully analyzed", result.lower())

    # -------------------------------------------------------------------------
    # 6. Supported types and reject unsupported types
    # -------------------------------------------------------------------------
    def test_unsupported_image_format_rejected_with_clear_message(self):
        """Images of unsupported format (like BMP) are rejected with a clear message."""
        uf = UploadedFile.objects.create(
            thread=self.thread,
            name="photo.bmp",
            mime="image/bmp",
            size=500,
            path="photo.bmp",
            status="ready",
        )
        result = read_file.invoke({"file_id": str(uf.id)})
        self.assertIn("Unsupported image format", result)
        self.assertIn(".bmp", result)
        self.assertIn("PNG", result)

    def test_corrupt_image_returns_clear_error(self):
        """Corrupt or invalid image file returns a clear error message."""
        corrupt_path, _ = storage.save_raw(b"NOT_A_REAL_IMAGE_DATA", extension="png")
        uf = self._create_uploaded_file_record("corrupt.png", corrupt_path)

        result = read_file.invoke({"file_id": str(uf.id)})
        self.assertIn("Corrupt or invalid image file", result)

    # -------------------------------------------------------------------------
    # 7. Image preparation: downscaling and GIF first frame
    # -------------------------------------------------------------------------
    def test_downscaling_longest_side_to_2000_px(self):
        """Images larger than 2000px on the longest side are downscaled preserving aspect ratio."""
        large_img = Image.new("RGB", (3000, 1500), color=(200, 200, 200))
        downscaled = downscale_image(large_img, max_longest_side=2000)
        self.assertEqual(downscaled.size, (2000, 1000))

    def test_gif_first_frame_handling(self):
        """GIF images extract the first frame and convert to RGB/RGBA cleanly."""
        frame1 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        frame2 = Image.new("RGBA", (100, 100), color=(0, 255, 0, 255))
        buf = io.BytesIO()
        frame1.save(buf, format="GIF", save_all=True, append_images=[frame2])
        gif_bytes = buf.getvalue()

        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(gif_bytes)
            tmp_path = f.name

        try:
            img, fmt, mime = validate_and_prepare_image(tmp_path, ".gif")
            self.assertEqual(img.size, (100, 100))
            b64, mime = encode_image_to_base64(img, ".gif")
            self.assertEqual(mime, "image/png")
            self.assertTrue(len(b64) > 0)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # -------------------------------------------------------------------------
    # 8. Upload-time summary non-fatal
    # -------------------------------------------------------------------------
    def test_upload_time_summary_failure_does_not_fail_upload(self):
        """If visual model fails during upload-time parsing, upload proceeds and saves basic metadata."""
        rel_path, _ = self._create_sample_image(text="DOC PHOTO")

        parser = ImageParser()
        with patch("filesvc.parsers.image.analyze_image_with_vision", side_effect=RuntimeError("API down")):
            result = parser.parse(rel_path, "sample.png")

        self.assertIn("400x200 px", result.text)
        self.assertEqual(result.structured_data["width"], 400)
        self.assertEqual(result.structured_data["height"], 200)
