import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from filesvc.generators.base import BaseGenerator

class ChartGenerator(BaseGenerator):
    """Generator for PNG charts from structured spec using matplotlib (Agg backend)."""
    default_extension = ".png"

    ALLOWED_TYPES = {"bar", "line", "pie", "scatter"}

    def validate_spec(self, spec: dict) -> None:
        super().validate_spec(spec)
        chart_type = str(spec.get("chart_type", "bar")).lower()
        if chart_type not in self.ALLOWED_TYPES:
            raise ValueError(f"Unsupported chart_type '{chart_type}'. Allowed types: {sorted(self.ALLOWED_TYPES)}.")

        has_data = bool(spec.get("x") or spec.get("labels") or spec.get("data") or spec.get("series"))
        if not has_data and not spec.get("y") and not spec.get("values"):
            raise ValueError("Chart spec must contain data points ('x'/'labels' and 'y'/'values').")

    def generate(self, spec: dict, output_path: str) -> None:
        self.validate_spec(spec)
        chart_type = str(spec.get("chart_type", "bar")).lower()
        title = spec.get("title", "")
        x_label = spec.get("x_label", "")
        y_label = spec.get("y_label", "")

        x_vals = spec.get("x") or spec.get("labels") or []
        y_vals = spec.get("y") or spec.get("values") or []

        fig, ax = plt.subplots(figsize=(8, 5), dpi=150)
        try:
            if chart_type == "bar":
                ax.bar(x_vals, y_vals, color="#3B82F6", edgecolor="#1D4ED8", alpha=0.85)
                if x_vals:
                    ax.set_xticks(range(len(x_vals)))
                    ax.set_xticklabels([str(v) for v in x_vals], rotation=30, ha="right")
            elif chart_type == "line":
                ax.plot(x_vals, y_vals, marker="o", color="#10B981", linewidth=2.5, markersize=6)
                if x_vals:
                    ax.set_xticks(range(len(x_vals)))
                    ax.set_xticklabels([str(v) for v in x_vals], rotation=30, ha="right")
            elif chart_type == "scatter":
                ax.scatter(x_vals, y_vals, color="#8B5CF6", s=60, alpha=0.8, edgecolors="none")
            elif chart_type == "pie":
                labels = [str(l) for l in x_vals] if x_vals else None
                ax.pie(y_vals, labels=labels, autopct="%1.1f%%", startangle=140)

            if chart_type != "pie":
                if title:
                    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
                if x_label:
                    ax.set_xlabel(x_label, fontsize=11)
                if y_label:
                    ax.set_ylabel(y_label, fontsize=11)
                if spec.get("grid", True):
                    ax.grid(True, linestyle="--", alpha=0.5)
            else:
                if title:
                    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)

            plt.tight_layout()
            fig.savefig(output_path, format="png")
        finally:
            plt.close(fig)

    def summarize_spec(self, spec: dict) -> str:
        chart_type = spec.get("chart_type", "bar")
        title = spec.get("title") or "Chart"
        items = len(spec.get("y") or spec.get("values") or [])
        return f"PNG Chart ({chart_type}) '{title}' [{items} point(s)]"
