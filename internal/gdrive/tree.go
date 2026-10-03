package gdrive

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"

	"github.com/Maxi49/Scrappy/internal/syncer"
)

// Tree is the last known shape of every Drive link, shown in the Drive panel.
type Tree struct {
	ScannedAt string  `json:"scanned_at"`
	Roots     []*Root `json:"roots"`
}

// Root is one Drive link found in Moodle.
type Root struct {
	ID       string `json:"id"`
	CourseID int    `json:"course_id"`
	Course   string `json:"materia"`
	Module   string `json:"modulo"`
	LinkName string `json:"link_name"`
	LinkURL  string `json:"link_url"`
	New      bool   `json:"new"`
	OAuth    bool   `json:"oauth"`
	Error    string `json:"error,omitempty"`
	Node     *Node  `json:"node,omitempty"`
}

const (
	KindFolder = "folder"
	KindFile   = "file"
	KindLink   = "link" // Forms, Sites and other files Drive cannot export
)

type Node struct {
	ID          string  `json:"id"`
	Name        string  `json:"name"`
	Kind        string  `json:"kind"`
	MIME        string  `json:"mime"`
	Size        int64   `json:"size"`
	Modified    int64   `json:"modified"`
	ResourceKey string  `json:"resource_key,omitempty"`
	Children    []*Node `json:"children,omitempty"`
}

func (r *Root) key() string { return rootKey(r.CourseID, r.Module, r.ID) }

func treePath(outputPath string) string {
	return filepath.Join(outputPath, syncer.MetadataDir, "drive-tree.json")
}

func LoadTree(outputPath string) (Tree, error) {
	content, err := os.ReadFile(treePath(outputPath))
	if errors.Is(err, os.ErrNotExist) {
		return Tree{}, nil
	}
	if err != nil {
		return Tree{}, err
	}
	var tree Tree
	if json.Unmarshal(content, &tree) != nil {
		return Tree{}, nil // a damaged snapshot is rebuilt by the next scan
	}
	return tree, nil
}

func SaveTree(outputPath string, tree Tree) error {
	content, err := json.MarshalIndent(tree, "", "  ")
	if err != nil {
		return err
	}
	return syncer.AtomicWrite(treePath(outputPath), content, 0o644)
}

// MergeTree replaces the roots of the courses this run analysed and keeps the
// rest, so syncing one course does not hide another course's Drive links.
func MergeTree(previous, current Tree, courseIDs []int) Tree {
	analysed := make(map[int]bool, len(courseIDs))
	for _, id := range courseIDs {
		analysed[id] = true
	}
	merged := Tree{ScannedAt: current.ScannedAt, Roots: append([]*Root(nil), current.Roots...)}
	for _, root := range previous.Roots {
		if !analysed[root.CourseID] {
			merged.Roots = append(merged.Roots, root)
		}
	}
	return merged
}
