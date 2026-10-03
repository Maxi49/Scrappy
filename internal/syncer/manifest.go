package syncer

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const manifestVersion = 2

type Manifest struct {
	Version int                        `json:"version"`
	Courses map[string]*ManifestCourse `json:"courses"`
}

type ManifestCourse struct {
	Name    string                     `json:"name"`
	Modules map[string]*ManifestModule `json:"modules"`
}

type ManifestModule struct {
	Name      string                       `json:"name"`
	Resources map[string]*ManifestResource `json:"resources"`
}

type ManifestResource struct {
	Fingerprint  string `json:"fingerprint"`
	RelativePath string `json:"relative_path"`
	Size         int64  `json:"size"`
	UpdatedAt    string `json:"updated_at"`
}

func newManifest() Manifest {
	return Manifest{Version: manifestVersion, Courses: make(map[string]*ManifestCourse)}
}

func loadManifest(path string) (Manifest, error) {
	content, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return newManifest(), nil
	}
	if err != nil {
		return Manifest{}, err
	}
	var manifest Manifest
	if err := json.Unmarshal(content, &manifest); err != nil {
		return newManifest(), nil
	}
	// Version 1 recorded a module hash before downloads completed and did not
	// retain local paths. It cannot prove that a file exists, so it is safer to
	// rebuild it once than to keep skipping missing files.
	if manifest.Version != manifestVersion || manifest.Courses == nil {
		return newManifest(), nil
	}
	return manifest, nil
}

func saveManifest(path string, manifest Manifest) error {
	manifest.Version = manifestVersion
	content, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return err
	}
	return atomicWrite(path, content, 0o600)
}

func (m *Manifest) module(courseID int, courseName, moduleName string, create bool) *ManifestModule {
	courseKey := courseKey(courseID)
	course := m.Courses[courseKey]
	if course == nil {
		if !create {
			return nil
		}
		course = &ManifestCourse{Name: courseName, Modules: make(map[string]*ManifestModule)}
		m.Courses[courseKey] = course
	}
	if course.Modules == nil {
		course.Modules = make(map[string]*ManifestModule)
	}
	moduleKey := normalizeKey(moduleName)
	module := course.Modules[moduleKey]
	if module == nil && create {
		module = &ManifestModule{Name: moduleName, Resources: make(map[string]*ManifestResource)}
		course.Modules[moduleKey] = module
	}
	return module
}

func (m *Manifest) markSuccess(courseID int, courseName, moduleName, resourceID, fingerprint, relativePath string, size int64) {
	module := m.module(courseID, courseName, moduleName, true)
	if module.Resources == nil {
		module.Resources = make(map[string]*ManifestResource)
	}
	module.Resources[resourceID] = &ManifestResource{
		Fingerprint: fingerprint, RelativePath: filepath.ToSlash(relativePath), Size: size,
		UpdatedAt: time.Now().UTC().Format(time.RFC3339),
	}
}

func courseKey(id int) string { return strconvItoa(id) }

func normalizeKey(value string) string {
	return strings.Join(strings.Fields(strings.ToLower(strings.TrimSpace(value))), " ")
}
