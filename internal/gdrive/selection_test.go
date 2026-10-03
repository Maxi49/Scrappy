package gdrive

import (
	"os"
	"path/filepath"
	"testing"
)

func TestNearestRuleWins(t *testing.T) {
	selection := Selection{Rules: map[string]string{"root": "include", "sub": "exclude", "keep": "include"}}
	cases := []struct {
		chain    []string
		included bool
	}{
		{[]string{"root"}, true},
		{[]string{"root", "a.pdf"}, true},
		{[]string{"root", "sub", "b.pdf"}, false},
		{[]string{"root", "sub", "keep", "c.pdf"}, true},
	}
	for _, tc := range cases {
		if got := selection.Included(tc.chain); got != tc.included {
			t.Errorf("Included(%v) = %v, want %v", tc.chain, got, tc.included)
		}
	}
}

func TestRootWithoutRuleIsNewAndNotDownloaded(t *testing.T) {
	selection := Selection{Rules: map[string]string{}}
	if selection.Included([]string{"root", "a.pdf"}) {
		t.Fatal("an unreviewed link was downloaded")
	}
	if !selection.IsNew("root") {
		t.Fatal("unreviewed root not marked new")
	}
	selection.Rules["root"] = "exclude"
	if selection.IsNew("root") {
		t.Fatal("reviewed root still marked new")
	}
}

func TestSelectionRoundTripsThroughTheMetadataFolder(t *testing.T) {
	output := t.TempDir()
	empty, err := LoadSelection(output)
	if err != nil || len(empty.Rules) != 0 {
		t.Fatalf("selection = %+v, err = %v", empty, err)
	}
	if err := SaveSelection(output, Selection{Rules: map[string]string{"root": "include"}}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(output, ".scrappy", "drive-selection.json")); err != nil {
		t.Fatal(err)
	}
	loaded, err := LoadSelection(output)
	if err != nil || loaded.Rules["root"] != "include" {
		t.Fatalf("selection = %+v, err = %v", loaded, err)
	}
}

func TestSaveSelectionRejectsUnknownRules(t *testing.T) {
	err := SaveSelection(t.TempDir(), Selection{Rules: map[string]string{"root": "maybe"}})
	if err == nil {
		t.Fatal("accepted an invalid rule")
	}
}

func TestMergeTreeKeepsCoursesOutsideThisRun(t *testing.T) {
	previous := Tree{ScannedAt: "old", Roots: []*Root{{ID: "A", CourseID: 1}, {ID: "B", CourseID: 2}}}
	current := Tree{ScannedAt: "new", Roots: []*Root{{ID: "C", CourseID: 1}}}
	merged := MergeTree(previous, current, []int{1})
	if merged.ScannedAt != "new" || len(merged.Roots) != 2 || merged.Roots[0].ID != "C" || merged.Roots[1].ID != "B" {
		t.Fatalf("merged = %+v", merged.Roots)
	}
}
