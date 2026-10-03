package syncer

import (
	"bytes"
	"crypto/sha256"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

// numberedCopy matches the "name_N.ext" copies Scrappy 0.1.x created whenever
// it downloaded a file that already existed. Four digits are left alone so a
// year such as parcial_2021.pdf is never mistaken for a copy.
var numberedCopy = regexp.MustCompile(`^(.+)_([0-9]{1,3})(\.[^.]*)?$`)

type Duplicate struct {
	Path     string `json:"path"`
	Original string `json:"original"`
	Size     int64  `json:"size"`
}

type DuplicateScan struct {
	Duplicates []Duplicate `json:"duplicates"`
	Bytes      int64       `json:"bytes"`
}

type SkippedDuplicate struct {
	Path   string `json:"path"`
	Reason string `json:"reason"`
}

type DuplicateRemoval struct {
	Removed []string           `json:"removed"`
	Skipped []SkippedDuplicate `json:"skipped"`
	Bytes   int64              `json:"bytes"`
}

// FindDuplicates lists numbered copies that are byte-identical to the original
// next to them. Files recorded in the manifest belong to a Moodle resource and
// are never reported, even if their name looks like a copy.
func FindDuplicates(outputPath string) (DuplicateScan, error) {
	scan := DuplicateScan{Duplicates: []Duplicate{}}
	root, tracked, err := duplicateContext(outputPath)
	if err != nil {
		return scan, err
	}
	err = filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			if path == root {
				return walkErr
			}
			return nil // unreadable folder: skip it, keep scanning the rest
		}
		if entry.IsDir() {
			if path != root && strings.HasPrefix(entry.Name(), ".") {
				return filepath.SkipDir
			}
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return nil
		}
		if duplicate, ok := identicalCopy(root, relative, tracked); ok {
			scan.Duplicates = append(scan.Duplicates, duplicate)
			scan.Bytes += duplicate.Size
		}
		return nil
	})
	sort.Slice(scan.Duplicates, func(i, j int) bool { return scan.Duplicates[i].Path < scan.Duplicates[j].Path })
	return scan, err
}

// RemoveDuplicates deletes the given relative paths, re-checking each one so a
// caller can never remove anything that is not an identical, untracked copy
// inside the output folder.
func RemoveDuplicates(outputPath string, paths []string) (DuplicateRemoval, error) {
	result := DuplicateRemoval{Removed: []string{}, Skipped: []SkippedDuplicate{}}
	root, tracked, err := duplicateContext(outputPath)
	if err != nil {
		return result, err
	}
	for _, requested := range paths {
		relative := filepath.FromSlash(requested)
		if !filepath.IsLocal(relative) || hasHiddenSegment(relative) {
			result.Skipped = append(result.Skipped, SkippedDuplicate{Path: requested, Reason: "fuera de la carpeta de destino"})
			continue
		}
		duplicate, ok := identicalCopy(root, relative, tracked)
		if !ok {
			result.Skipped = append(result.Skipped, SkippedDuplicate{Path: requested, Reason: "ya no es una copia idéntica"})
			continue
		}
		if err := os.Remove(filepath.Join(root, relative)); err != nil {
			result.Skipped = append(result.Skipped, SkippedDuplicate{Path: requested, Reason: err.Error()})
			continue
		}
		result.Removed = append(result.Removed, duplicate.Path)
		result.Bytes += duplicate.Size
	}
	return result, nil
}

func duplicateContext(outputPath string) (string, map[string]bool, error) {
	if strings.TrimSpace(outputPath) == "" {
		return "", nil, errors.New("falta la carpeta de destino")
	}
	root, err := filepath.Abs(outputPath)
	if err != nil {
		return "", nil, err
	}
	if info, err := os.Stat(root); err != nil || !info.IsDir() {
		return "", nil, errors.New("la carpeta de destino no existe")
	}
	tracked := make(map[string]bool)
	for _, candidate := range []string{
		filepath.Join(root, MetadataDir, "manifest.json"),
		filepath.Join(root, "config", "manifest.json"),
	} {
		if _, err := os.Stat(candidate); err != nil {
			continue
		}
		manifest, err := loadManifest(candidate)
		if err != nil {
			return "", nil, err
		}
		for _, course := range manifest.Courses {
			for _, module := range course.Modules {
				for _, entry := range module.Resources {
					if entry != nil && entry.RelativePath != "" {
						tracked[pathKey(filepath.FromSlash(entry.RelativePath))] = true
					}
				}
			}
		}
	}
	return root, tracked, nil
}

func identicalCopy(root, relative string, tracked map[string]bool) (Duplicate, bool) {
	match := numberedCopy.FindStringSubmatch(filepath.Base(relative))
	if match == nil || tracked[pathKey(relative)] {
		return Duplicate{}, false
	}
	originalRelative := filepath.Join(filepath.Dir(relative), match[1]+match[3])
	copyPath, originalPath := filepath.Join(root, relative), filepath.Join(root, originalRelative)
	copyInfo, err := os.Lstat(copyPath)
	if err != nil || !copyInfo.Mode().IsRegular() {
		return Duplicate{}, false
	}
	originalInfo, err := os.Lstat(originalPath)
	if err != nil || !originalInfo.Mode().IsRegular() || originalInfo.Size() != copyInfo.Size() {
		return Duplicate{}, false
	}
	if os.SameFile(copyInfo, originalInfo) || !sameContent(copyPath, originalPath) {
		return Duplicate{}, false
	}
	return Duplicate{
		Path: filepath.ToSlash(relative), Original: filepath.ToSlash(originalRelative), Size: copyInfo.Size(),
	}, true
}

func sameContent(first, second string) bool {
	a, errA := fileHash(first)
	b, errB := fileHash(second)
	return errA == nil && errB == nil && bytes.Equal(a, b)
}

func fileHash(path string) ([]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return nil, err
	}
	return hash.Sum(nil), nil
}

func hasHiddenSegment(relative string) bool {
	for _, segment := range strings.Split(relative, string(filepath.Separator)) {
		if strings.HasPrefix(segment, ".") {
			return true
		}
	}
	return false
}
