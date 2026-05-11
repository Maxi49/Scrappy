import importlib.util
from pathlib import Path


def load_package_artifact_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "package_artifact.py"
    spec = importlib.util.spec_from_file_location("package_artifact", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_macos_app_archives_with_ditto(monkeypatch, tmp_path):
    module = load_package_artifact_module()
    app_path = tmp_path / "dist" / "Scrappy.app"
    app_path.mkdir(parents=True)
    archive_base = tmp_path / "artifacts" / "Scrappy-macos-apple-silicon"
    archive_base.parent.mkdir()
    calls = []

    def fake_run(command, check):
        calls.append((command, check))

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    archive_path = module.make_archive(app_path, archive_base, system="Darwin")

    assert archive_path == str(archive_base.with_suffix(".zip"))
    assert calls == [
        (
            [
                "ditto",
                "-c",
                "-k",
                "--sequesterRsrc",
                "--keepParent",
                str(app_path),
                str(archive_base.with_suffix(".zip")),
            ],
            True,
        )
    ]


def test_non_macos_archives_with_shutil(monkeypatch, tmp_path):
    module = load_package_artifact_module()
    app_path = tmp_path / "dist" / "Scrappy"
    app_path.parent.mkdir()
    app_path.write_text("binary")
    archive_base = tmp_path / "artifacts" / "Scrappy-linux"
    archive_base.parent.mkdir()

    def fake_make_archive(base_name, format_name, root_dir, base_dir):
        return f"{base_name}.{format_name}"

    monkeypatch.setattr(module.shutil, "make_archive", fake_make_archive)

    archive_path = module.make_archive(app_path, archive_base, system="Linux")

    assert archive_path == f"{archive_base}.zip"
