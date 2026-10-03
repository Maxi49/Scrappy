package gdrive

import "testing"

func TestParseLink(t *testing.T) {
	cases := []struct {
		raw  string
		want Link
		ok   bool
	}{
		{"https://drive.google.com/drive/folders/FOLDER1?usp=sharing", Link{ID: "FOLDER1", Folder: true}, true},
		{"https://drive.google.com/drive/u/1/folders/FOLDER2", Link{ID: "FOLDER2", Folder: true}, true},
		{"https://drive.google.com/drive/folders/F3?resourcekey=0-abc", Link{ID: "F3", Folder: true, ResourceKey: "0-abc"}, true},
		{"https://drive.google.com/file/d/FILE1/view?usp=drive_link", Link{ID: "FILE1"}, true},
		{"https://drive.google.com/open?id=FILE2", Link{ID: "FILE2"}, true},
		{"https://drive.google.com/uc?id=FILE3&export=download", Link{ID: "FILE3"}, true},
		{"https://docs.google.com/document/d/DOC1/edit", Link{ID: "DOC1"}, true},
		{"https://docs.google.com/spreadsheets/d/SHEET1/edit#gid=0", Link{ID: "SHEET1"}, true},
		{"https://docs.google.com/presentation/d/PRES1/edit?resourcekey=0-k", Link{ID: "PRES1", ResourceKey: "0-k"}, true},
		{"https://docs.google.com/drawings/d/DRAW1/edit", Link{ID: "DRAW1"}, true},
		{"https://docs.google.com/forms/d/e/FORM1/viewform", Link{}, false},
		{"https://drive.google.com/drive/my-drive", Link{}, false},
		{"https://example.com/folders/X", Link{}, false},
	}
	for _, tc := range cases {
		got, ok := ParseLink(tc.raw)
		if ok != tc.ok || got != tc.want {
			t.Errorf("ParseLink(%q) = %+v, %v; want %+v, %v", tc.raw, got, ok, tc.want, tc.ok)
		}
	}
}
