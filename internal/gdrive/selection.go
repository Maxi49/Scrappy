package gdrive

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/Maxi49/Scrappy/internal/syncer"
)

const (
	RuleInclude = "include"
	RuleExclude = "exclude"
)

// Selection holds the student's Drive choices as rules keyed by Drive ID.
// A node follows the nearest rule among itself and its ancestors; a link
// without any rule downloads nothing until the student reviews it.
type Selection struct {
	Version int               `json:"version"`
	Rules   map[string]string `json:"rules"`
}

func selectionPath(outputPath string) string {
	return filepath.Join(outputPath, syncer.MetadataDir, "drive-selection.json")
}

// Included reports whether the last ID in chain (root first) is selected.
func (s Selection) Included(chain []string) bool {
	for index := len(chain) - 1; index >= 0; index-- {
		if rule, ok := s.Rules[chain[index]]; ok {
			return rule == RuleInclude
		}
	}
	return false
}

// IsNew reports whether the student has not reviewed this link yet.
func (s Selection) IsNew(rootID string) bool {
	_, reviewed := s.Rules[rootID]
	return !reviewed
}

func LoadSelection(outputPath string) (Selection, error) {
	selection := Selection{Version: 1, Rules: map[string]string{}}
	content, err := os.ReadFile(selectionPath(outputPath))
	if errors.Is(err, os.ErrNotExist) {
		return selection, nil
	}
	if err != nil {
		return selection, err
	}
	if err := json.Unmarshal(content, &selection); err != nil {
		return Selection{Version: 1, Rules: map[string]string{}}, fmt.Errorf("leer selección de Drive: %w", err)
	}
	if selection.Rules == nil {
		selection.Rules = map[string]string{}
	}
	return selection, nil
}

func SaveSelection(outputPath string, selection Selection) error {
	for id, rule := range selection.Rules {
		if id == "" || (rule != RuleInclude && rule != RuleExclude) {
			return fmt.Errorf("regla de Drive inválida para %q: %q", id, rule)
		}
	}
	if selection.Rules == nil {
		selection.Rules = map[string]string{}
	}
	selection.Version = 1
	content, err := json.MarshalIndent(selection, "", "  ")
	if err != nil {
		return err
	}
	return syncer.AtomicWrite(selectionPath(outputPath), content, 0o644)
}
