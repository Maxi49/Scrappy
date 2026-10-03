package syncer

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeTree(t *testing.T, root string, files map[string]string) {
	t.Helper()
	for relative, content := range files {
		path := filepath.Join(root, filepath.FromSlash(relative))
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

func TestFindDuplicatesOnlyReportsIdenticalNumberedCopies(t *testing.T) {
	root := t.TempDir()
	writeTree(t, root, map[string]string{
		"Materia/Unidad 1/apunte.pdf":       "version nueva",
		"Materia/Unidad 1/apunte_1.pdf":     "version nueva", // identical → duplicate
		"Materia/Unidad 1/apunte_2.pdf":     "version vieja", // differs → keep
		"Materia/Unidad 1/guia_1.pdf":       "sin original",  // no original → keep
		"Materia/Unidad 1/tp_3":             "x",             // no extension
		"Materia/Unidad 1/tp":               "x",
		"Materia/Unidad 2/parcial_2021.pdf": "examen", // year, not a copy
		"Materia/Unidad 2/parcial.pdf":      "otro",
		".scrappy/sync-report_1.json":       "{}",
		".scrappy/sync-report.json":         "{}",
	})
	scan, err := FindDuplicates(root)
	if err != nil {
		t.Fatal(err)
	}
	var paths []string
	for _, duplicate := range scan.Duplicates {
		paths = append(paths, duplicate.Path)
	}
	if got := strings.Join(paths, ","); got != "Materia/Unidad 1/apunte_1.pdf,Materia/Unidad 1/tp_3" {
		t.Fatalf("unexpected duplicates: %s", got)
	}
	if scan.Duplicates[0].Original != "Materia/Unidad 1/apunte.pdf" || scan.Bytes != int64(len("version nueva")+1) {
		t.Fatalf("unexpected scan details: %#v", scan)
	}
}

func TestFindDuplicatesNeverReportsFilesTheManifestTracks(t *testing.T) {
	root := t.TempDir()
	writeTree(t, root, map[string]string{
		"Materia/Unidad/nodo.h":   "same",
		"Materia/Unidad/nodo_1.h": "same",
	})
	manifest := newManifest()
	manifest.markSuccess(7, "Materia", "Unidad", "resource-b", "fp", "Materia/Unidad/nodo_1.h", 4)
	if err := saveManifest(filepath.Join(root, MetadataDir, "manifest.json"), manifest); err != nil {
		t.Fatal(err)
	}
	scan, err := FindDuplicates(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(scan.Duplicates) != 0 {
		t.Fatalf("a file Moodle owns was reported as duplicate: %#v", scan.Duplicates)
	}
}

func TestRemoveDuplicatesRechecksEveryPath(t *testing.T) {
	root := t.TempDir()
	outside := t.TempDir()
	writeTree(t, root, map[string]string{
		"Materia/U/apunte.pdf":   "igual",
		"Materia/U/apunte_1.pdf": "igual",
		"Materia/U/resumen.pdf":  "mio",
	})
	writeTree(t, outside, map[string]string{"secreto_1.txt": "a", "secreto.txt": "a"})
	escape, _ := filepath.Rel(root, filepath.Join(outside, "secreto_1.txt"))

	result, err := RemoveDuplicates(root, []string{
		"Materia/U/apunte_1.pdf", "Materia/U/resumen.pdf", "Materia/U/apunte.pdf", filepath.ToSlash(escape),
		filepath.Join(outside, "secreto_1.txt"),
	})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Join(result.Removed, ",") != "Materia/U/apunte_1.pdf" || result.Bytes != 5 || len(result.Skipped) != 4 {
		t.Fatalf("unexpected result: %#v", result)
	}
	for _, kept := range []string{
		filepath.Join(root, "Materia/U/apunte.pdf"), filepath.Join(root, "Materia/U/resumen.pdf"),
		filepath.Join(outside, "secreto_1.txt"),
	} {
		if _, err := os.Stat(kept); err != nil {
			t.Fatalf("%s should not have been removed", kept)
		}
	}
}
