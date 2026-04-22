from __future__ import annotations

from pathlib import Path

from flask import Flask, redirect, render_template, request, send_file, url_for

from lead_engine import (
    ALL_BUSINESSES_QUERY,
    DEFAULT_CITY,
    DEFAULT_MAX_BUSINESSES,
    DEFAULT_MAX_IMAGES,
    DEFAULT_NICHE,
    DEFAULT_QUERY,
    DEFAULT_SERVICE,
    NICHE_CONFIGS,
    ScanConfig,
    preview_discovery,
    run_scan_report,
)


APP_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = APP_ROOT / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        config = ScanConfig(
            city=request.form.get("city", DEFAULT_CITY),
            query=request.form.get("query", DEFAULT_QUERY).strip(),
            niche=request.form.get("niche", DEFAULT_NICHE),
            max_businesses=int(request.form.get("max_businesses", DEFAULT_MAX_BUSINESSES)),
            max_images=int(request.form.get("max_images", DEFAULT_MAX_IMAGES)),
            service_offer=request.form.get("service_offer", DEFAULT_SERVICE),
            min_score=int(request.form.get("min_score", 0)),
        )

        base_name = f"lead_run_{config.niche}"
        config.output_csv = str(RUNTIME_DIR / f"{base_name}.csv")
        config.output_md = str(RUNTIME_DIR / f"{base_name}.md")
        config.output_db = str(RUNTIME_DIR / f"{base_name}.db")

        uploaded = request.files.get("source_csv")
        websites_text = request.form.get("websites", "").strip()
        action = request.form.get("action", "scan")

        if action == "all-businesses":
            config.query = ALL_BUSINESSES_QUERY
            config.niche = "default"

        if uploaded and uploaded.filename:
            temp_path = RUNTIME_DIR / "uploaded_source.csv"
            temp_path.write_bytes(uploaded.read())
            config.source_csv = str(temp_path)
        elif websites_text:
            config.websites_arg = websites_text.replace("\n", ",")

        if action == "discover":
            attempts = preview_discovery(config)
            discovered_websites = [attempt.discovered_website for attempt in attempts if attempt.discovered_website]
            return render_template(
                "discover.html",
                attempts=attempts,
                config=config,
                discovered_websites=discovered_websites,
            )

        report = run_scan_report(config)
        leads = report.leads
        return render_template(
            "results.html",
            leads=leads,
            attempts=report.attempts,
            config=config,
            csv_name=Path(config.output_csv).name if leads else None,
            md_name=Path(config.output_md).name if leads else None,
        )

    return render_template(
        "index.html",
        niches=sorted(NICHE_CONFIGS.keys()),
        defaults={
            "city": DEFAULT_CITY,
            "query": DEFAULT_QUERY,
            "niche": DEFAULT_NICHE,
            "max_businesses": DEFAULT_MAX_BUSINESSES,
            "max_images": DEFAULT_MAX_IMAGES,
            "service_offer": DEFAULT_SERVICE,
            "min_score": 25,
        },
    )


@app.route("/score-candidates", methods=["POST"])
def score_candidates():
    config = ScanConfig(
        city=request.form.get("city", DEFAULT_CITY),
        query=request.form.get("query", DEFAULT_QUERY).strip(),
        niche=request.form.get("niche", DEFAULT_NICHE),
        max_businesses=int(request.form.get("max_businesses", DEFAULT_MAX_BUSINESSES)),
        max_images=int(request.form.get("max_images", DEFAULT_MAX_IMAGES)),
        service_offer=request.form.get("service_offer", DEFAULT_SERVICE),
        min_score=int(request.form.get("min_score", 0)),
    )

    base_name = f"lead_run_{config.niche}"
    config.output_csv = str(RUNTIME_DIR / f"{base_name}.csv")
    config.output_md = str(RUNTIME_DIR / f"{base_name}.md")
    config.output_db = str(RUNTIME_DIR / f"{base_name}.db")
    config.websites_arg = request.form.get("websites", "")

    report = run_scan_report(config)
    leads = report.leads
    return render_template(
        "results.html",
        leads=leads,
        attempts=report.attempts,
        config=config,
        csv_name=Path(config.output_csv).name if leads else None,
        md_name=Path(config.output_md).name if leads else None,
    )


@app.route("/download/<path:filename>")
def download(filename: str):
    path = RUNTIME_DIR / filename
    if not path.exists():
        return redirect(url_for("index"))
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True, port=5050)
