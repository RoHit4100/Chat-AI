import os
import json
import tempfile
from pathlib import Path
from django.test import TestCase
from django.contrib.auth import get_user_model
from langchain_core.messages import AIMessage, HumanMessage

from chat.models import Thread, GeneratedFile
from filesvc.generators.pdf_gen import PdfGenerator
from filesvc.generators.docx_gen import DocxGenerator
from filesvc.generators.verification import verify_generated_file
from agent.tools import generate_file
from agent.nodes import tools_node

User = get_user_model()

class FileGenerationQualityTests(TestCase):
    """Tests covering file generation quality, Unicode rendering, pagination, verification, and revision flows."""

    def setUp(self):
        self.user = User.objects.create_user(username="quality_tester", password="password123")
        self.thread = Thread.objects.create(user=self.user, title="Resume Generation Thread")

    def test_resume_spec_renders_valid_pdf_with_all_sections_and_bullets(self):
        """A resume-style spec renders to a valid PDF with all sections, groups, entries, and bullets."""
        spec = {
            "title": "Rohit L. Udamale",
            "subtitle": "Backend & React Native Developer",
            "header": ["9373369378", "rohitudamale777@gmail.com", "Thane, Mumbai, India", "LinkedIn", "GitHub"],
            "sections": [
                {
                    "heading": "Summary",
                    "content": "Backend-focused Software Engineer with 2+ years building high-performance systems and React Native apps."
                },
                {
                    "heading": "Technical Skills",
                    "groups": [
                        {"label": "Backend:", "items": "Django, DRF, REST APIs, Celery, Java, Spring Boot"},
                        {"label": "Mobile & Frontend:", "items": "React Native, React, JavaScript, HTML5, CSS3"},
                        {"label": "Cloud & DevOps:", "items": "AWS, Docker, Kubernetes, CI/CD"},
                    ]
                },
                {
                    "heading": "Work Experience",
                    "entries": [
                        {
                            "title": "Solution Analyst",
                            "subtitle": "Sankey Solutions",
                            "date": "Sept 2024 - Present",
                            "location": "Mumbai, India",
                            "bullets": [
                                "Architected scalable backend microservices using Django and PostgreSQL.",
                                "Developed cross-platform React Native features for mobile clients.",
                                "Implemented authentication and token management with Keycloak."
                            ]
                        }
                    ]
                },
                {
                    "heading": "Education",
                    "entries": [
                        {
                            "title": "Bachelor of Engineering in Information Technology",
                            "subtitle": "University of Mumbai",
                            "date": "2020 - 2024",
                            "bullets": ["Graduated with distinction."]
                        }
                    ]
                }
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            gen = PdfGenerator()
            gen.generate(spec, tmp_path)

            metrics = verify_generated_file("pdf", tmp_path, spec)
            self.assertEqual(metrics["pages"], 1)
            self.assertEqual(metrics["sections"], 4)
            self.assertGreater(metrics["words"], 80)

            # Check extracted text contains all key sections
            import pypdf
            reader = pypdf.PdfReader(tmp_path)
            extracted = "".join(p.extract_text() for p in reader.pages)
            self.assertIn("Rohit L. Udamale", extracted)
            self.assertIn("Backend & React Native Developer", extracted)
            self.assertIn("SUMMARY", extracted.upper())
            self.assertIn("TECHNICAL SKILLS", extracted.upper())
            self.assertIn("WORK EXPERIENCE", extracted.upper())
            self.assertIn("EDUCATION", extracted.upper())
            self.assertIn("Sankey Solutions", extracted)
            self.assertIn("Django", extracted)
            self.assertIn("React Native", extracted)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_resume_spec_renders_valid_docx_with_all_sections_and_bullets(self):
        """A resume-style spec renders to a valid DOCX with all sections and bullets."""
        spec = {
            "title": "Rohit L. Udamale",
            "subtitle": "Backend Developer",
            "header": ["9373369378", "rohitudamale777@gmail.com", "Mumbai"],
            "sections": [
                {
                    "heading": "Summary",
                    "content": "Experienced backend engineer."
                },
                {
                    "heading": "Technical Skills",
                    "groups": [
                        {"label": "Languages:", "items": "Python, Java, TypeScript"}
                    ]
                },
                {
                    "heading": "Experience",
                    "entries": [
                        {
                            "title": "Software Engineer",
                            "subtitle": "Tech Corp",
                            "date": "2023 - Present",
                            "bullets": ["Built robust REST APIs with Django."]
                        }
                    ]
                }
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            gen = DocxGenerator()
            gen.generate(spec, tmp_path)

            metrics = verify_generated_file("docx", tmp_path, spec)
            self.assertGreaterEqual(metrics["pages"], 1)
            self.assertEqual(metrics["sections"], 3)
            self.assertGreater(metrics["words"], 20)

            import docx
            doc = docx.Document(tmp_path)
            all_text = " ".join(p.text for p in doc.paragraphs)
            self.assertIn("Rohit L. Udamale", all_text)
            self.assertIn("EXPERIENCE", all_text.upper())
            self.assertIn("Built robust REST APIs", all_text)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_long_content_paginates(self):
        """Long content with multiple paragraphs properly paginates across 2 or more pages in PDF."""
        long_paragraphs = [
            f"Paragraph {i}: " + ("This is detailed enterprise software engineering documentation. " * 15)
            for i in range(1, 20)
        ]
        spec = {
            "title": "Comprehensive Architecture Document",
            "sections": [
                {
                    "heading": f"Section {i}",
                    "paragraphs": [long_paragraphs[i - 1], long_paragraphs[i]]
                }
                for i in range(1, 10)
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            gen = PdfGenerator()
            gen.generate(spec, tmp_path)

            import pypdf
            reader = pypdf.PdfReader(tmp_path)
            self.assertGreaterEqual(len(reader.pages), 2, "Long content should produce 2 or more pages.")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_unicode_characters_render(self):
        """Unicode characters (bullets, em-dashes, non-Latin text) render without error in PDF and DOCX."""
        spec = {
            "title": "Unicode Résumé — International",
            "header": ["contact@example.com • +91-9373369378 • Mumbai — India"],
            "sections": [
                {
                    "heading": "Languages & Glyphs",
                    "content": "Special characters: — – • → © ® ™. Non-Latin: नमस्ते, 日本語, résumé, naïve.",
                    "bullets": [
                        "Em-dash: 2024 — 2026",
                        "Arrow bullet: Service A → Service B",
                        "Hindi text: इंजीनियर"
                    ]
                }
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            pdf_path = tmp_pdf.name
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_docx:
            docx_path = tmp_docx.name

        try:
            pdf_gen = PdfGenerator()
            pdf_gen.generate(spec, pdf_path)
            self.assertTrue(os.path.getsize(pdf_path) > 0)

            docx_gen = DocxGenerator()
            docx_gen.generate(spec, docx_path)
            self.assertTrue(os.path.getsize(docx_path) > 0)
        finally:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
            if os.path.exists(docx_path):
                os.unlink(docx_path)

    def test_truncated_spec_retried(self):
        """Truncated or invalid JSON spec in generate_file surfaces a retry message, and tools_node handles invalid tool calls."""
        cfg = {"configurable": {"thread_id": str(self.thread.id), "user_id": str(self.user.id)}}

        # Truncated JSON string
        truncated_spec_str = '{"title": "Broken Resume", "sections": [{"heading": "Summary", "content": "incompl'
        res = generate_file.invoke({"kind": "pdf", "name": "test.pdf", "spec": truncated_spec_str}, config=cfg)
        self.assertIn("spec was truncated or invalid JSON", res)
        self.assertIn("Please retry once with a more compact spec", res)

        # Invalid tool call on AIMessage handled by tools_node
        invalid_msg = AIMessage(
            content="",
            invalid_tool_calls=[{
                "name": "generate_file",
                "args": "{\"kind\": \"pdf\", \"name\": \"broken.pdf\", \"spec\": ",
                "id": "call_invalid_1",
                "error": "Invalid json",
            }]
        )
        import asyncio
        node_res = asyncio.run(tools_node({"messages": [invalid_msg], "tool_errors": 0}, config=cfg))
        synthesized = node_res["messages"][-1]
        self.assertEqual(synthesized.status, "error")
        self.assertIn("truncated or invalid JSON", synthesized.content)
        self.assertIn("Please retry once with a more compact spec", synthesized.content)

    def test_verification_catches_empty_section(self):
        """Verification catches when a section heading is not found or has no content."""
        spec_missing_content = {
            "title": "Document",
            "sections": [
                {"heading": "Missing Heading Never Rendered", "content": ""}
            ]
        }

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            gen = PdfGenerator()
            # If we generate an empty document and verify with a spec requiring a section that wasn't rendered:
            gen.generate({"title": "Empty Document", "paragraphs": ["Some text"]}, tmp_path)
            with self.assertRaises(ValueError) as ctx:
                verify_generated_file("pdf", tmp_path, spec_missing_content)
            self.assertIn("Verification failed: section 'Missing Heading Never Rendered' is missing", str(ctx.exception))
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_revision_flow_creates_version_2(self):
        """Revision flow with based_on creates version 2 linked to parent file."""
        cfg = {"configurable": {"thread_id": str(self.thread.id), "user_id": str(self.user.id)}}

        spec_v1 = {
            "title": "Initial Resume",
            "sections": [
                {"heading": "Summary", "content": "Full lengthy summary paragraph."}
            ]
        }
        res_v1 = generate_file.invoke({"kind": "pdf", "name": "Resume.pdf", "spec": spec_v1}, config=cfg)
        self.assertIn("Successfully generated", res_v1)
        self.assertIn("version: 1", res_v1)

        v1 = GeneratedFile.objects.filter(thread=self.thread, name="Resume.pdf", version=1).first()
        self.assertIsNotNone(v1)

        spec_v2 = {
            "title": "Concise Resume",
            "sections": [
                {"heading": "Summary", "content": "Shorter summary."},
                {"heading": "Skills", "bullets": ["Python", "Django"]}
            ]
        }
        res_v2 = generate_file.invoke(
            {"kind": "pdf", "name": "Resume.pdf", "spec": spec_v2, "based_on": v1.id},
            config=cfg
        )
        self.assertIn("Successfully generated", res_v2)
        self.assertIn("version: 2", res_v2)

        v2 = GeneratedFile.objects.filter(thread=self.thread, name="Resume.pdf", version=2).first()
        self.assertIsNotNone(v2)
        self.assertEqual(v2.parent_id, v1.id)
        self.assertEqual(v2.version, 2)
        self.assertNotEqual(v1.path, v2.path)
