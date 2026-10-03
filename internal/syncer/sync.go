package syncer

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

type Mode struct {
	Name         string `json:"mode"`
	ScanExisting bool   `json:"scan_existing"`
}

type Options struct {
	OutputPath   string
	Modes        map[int]Mode
	Workers      int
	Progress     moodle.ProgressFunc
	WriteIndexes bool
}

type Failure struct {
	Course   string `json:"materia"`
	Module   string `json:"modulo"`
	Resource string `json:"recurso"`
	Error    string `json:"error"`
}

type Report struct {
	StartedAt    string             `json:"started_at"`
	FinishedAt   string             `json:"finished_at"`
	Discovered   int                `json:"discovered"`
	Downloaded   int                `json:"downloaded"`
	LinksSaved   int                `json:"links_saved"`
	Unchanged    int                `json:"unchanged"`
	Skipped      int                `json:"skipped"`
	Inaccessible int                `json:"inaccessible"`
	Failed       int                `json:"failed"`
	Cancelled    bool               `json:"cancelled,omitempty"`
	Failures     []Failure          `json:"failures,omitempty"`
	Diagnostics  moodle.Diagnostics `json:"api_diagnostics"`
}

type job struct {
	resource    moodle.Resource
	relative    string
	destination string
	fingerprint string
}

type outcome struct {
	job    job
	status string
	size   int64
	err    error
}

func Run(ctx context.Context, client *moodle.Client, catalog moodle.Catalog, options Options) (Report, error) {
	start := time.Now().UTC()
	report := Report{StartedAt: start.Format(time.RFC3339), Discovered: len(catalog.Resources), Diagnostics: catalog.Diagnostics}
	if strings.TrimSpace(options.OutputPath) == "" {
		return report, fmt.Errorf("falta la carpeta de salida")
	}
	outputPath, err := filepath.Abs(options.OutputPath)
	if err != nil {
		return report, err
	}
	if err := os.MkdirAll(outputPath, 0o755); err != nil {
		return report, fmt.Errorf("crear carpeta de salida: %w", err)
	}
	manifestPath := filepath.Join(outputPath, "config", "manifest.json")
	manifest, err := loadManifest(manifestPath)
	if err != nil {
		return report, fmt.Errorf("leer manifiesto: %w", err)
	}
	for _, failure := range catalog.Diagnostics.CourseErrors {
		report.Failed++
		report.Failures = append(report.Failures, Failure{
			Course: failure.Course, Error: "no se pudo analizar la materia: " + failure.Error,
		})
	}
	destinations := planDestinations(catalog.Resources, manifest)
	jobs := make([]job, 0, len(catalog.Resources))

	for _, resource := range catalog.Resources {
		relative := destinations[resource.ID]
		planned := job{resource: resource, relative: relative, destination: filepath.Join(outputPath, relative), fingerprint: fingerprint(resource)}
		if !resource.Accessible {
			report.Inaccessible++
			continue
		}
		mode := options.Modes[resource.CourseID]
		if mode.Name == "" {
			mode = Mode{Name: "update", ScanExisting: true}
		}
		module := manifest.module(resource.CourseID, resource.CourseName, resource.ModuleName, false)
		if mode.Name == "update" && !mode.ScanExisting && module != nil {
			report.Skipped++
			continue
		}
		if mode.Name != "full" && module != nil {
			entry := module.Resources[resource.ID]
			if entry != nil && entry.Fingerprint == planned.fingerprint && localEntryValid(outputPath, entry, resource) {
				report.Unchanged++
				continue
			}
		}
		jobs = append(jobs, planned)
	}

	workers := options.Workers
	if workers <= 0 {
		workers = 12
	}
	if workers > 24 {
		workers = 24
	}
	jobChannel := make(chan job)
	outcomes := make(chan outcome, len(jobs))
	var wait sync.WaitGroup
	for index := 0; index < workers; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			for current := range jobChannel {
				var size int64
				var err error
				status := "downloaded"
				if current.resource.IsLink() {
					status = "link"
					size, err = writeShortcut(current.destination, current.resource.URL)
				} else {
					size, err = downloadFile(ctx, client, current.resource, current.destination)
				}
				outcomes <- outcome{job: current, status: status, size: size, err: err}
			}
		}()
	}
	go func() {
	feed:
		for _, current := range jobs {
			select {
			case jobChannel <- current:
			case <-ctx.Done():
				break feed
			}
		}
		close(jobChannel)
		wait.Wait()
		close(outcomes)
	}()

	for result := range outcomes {
		resource := result.job.resource
		if result.err != nil && ctx.Err() != nil {
			// Interrupted by the user, not a Moodle failure; the next sync
			// simply picks this resource up again.
			continue
		}
		if result.err != nil {
			report.Failed++
			report.Failures = append(report.Failures, Failure{
				Course: resource.CourseName, Module: resource.ModuleName,
				Resource: resource.Name, Error: result.err.Error(),
			})
			if options.Progress != nil {
				options.Progress(fmt.Sprintf("✗ %s: %s", resource.Name, result.err))
			}
			continue
		}
		if result.status == "link" {
			report.LinksSaved++
		} else {
			report.Downloaded++
		}
		manifest.markSuccess(resource.CourseID, resource.CourseName, resource.ModuleName, resource.ID, result.job.fingerprint, result.job.relative, result.size)
		if options.Progress != nil {
			options.Progress(fmt.Sprintf("✓ %s", resource.Name))
		}
	}

	sort.Slice(report.Failures, func(i, j int) bool {
		a, b := report.Failures[i], report.Failures[j]
		if a.Course != b.Course {
			return a.Course < b.Course
		}
		if a.Module != b.Module {
			return a.Module < b.Module
		}
		return a.Resource < b.Resource
	})
	if err := saveManifest(manifestPath, manifest); err != nil {
		return report, fmt.Errorf("guardar manifiesto: %w", err)
	}
	report.FinishedAt = time.Now().UTC().Format(time.RFC3339)
	report.Cancelled = ctx.Err() != nil
	if err := writeExports(outputPath, catalog.Resources, report, options.WriteIndexes); err != nil {
		return report, fmt.Errorf("exportar resultados: %w", err)
	}
	if report.Cancelled {
		return report, fmt.Errorf("sincronización cancelada: %w", ctx.Err())
	}
	if report.Failed > 0 {
		return report, fmt.Errorf("%d materia(s) o recurso(s) fallaron; ver sync-report.json", report.Failed)
	}
	return report, nil
}

func localEntryValid(outputPath string, entry *ManifestResource, resource moodle.Resource) bool {
	if entry.RelativePath == "" {
		return false
	}
	target := filepath.Join(outputPath, filepath.FromSlash(entry.RelativePath))
	info, err := os.Stat(target)
	if err != nil || !info.Mode().IsRegular() || info.Size() == 0 {
		return false
	}
	if resource.IsLink() {
		return true
	}
	if resource.Size > 0 && info.Size() != resource.Size {
		return false
	}
	return true
}

func writeExports(outputPath string, resources []moodle.Resource, report Report, writeIndexes bool) error {
	if writeIndexes {
		resourceJSON, err := json.MarshalIndent(resources, "", "  ")
		if err != nil {
			return err
		}
		if err := atomicWrite(filepath.Join(outputPath, "recursos_encontrados.json"), resourceJSON, 0o644); err != nil {
			return err
		}
		var text strings.Builder
		text.WriteString("RECURSOS ENCONTRADOS EN MOODLE UCC\n")
		text.WriteString(strings.Repeat("=", 80) + "\n\n")
		lastCourse, lastModule := "", ""
		for _, resource := range resources {
			if resource.CourseName != lastCourse {
				lastCourse, lastModule = resource.CourseName, ""
				text.WriteString("\nMATERIA: " + lastCourse + "\n" + strings.Repeat("=", 80) + "\n")
			}
			if resource.ModuleName != lastModule {
				lastModule = resource.ModuleName
				text.WriteString("\n  MÓDULO: " + lastModule + "\n")
			}
			text.WriteString("    - " + resource.Name + " [" + string(resource.Type) + "]\n")
		}
		if err := atomicWrite(filepath.Join(outputPath, "recursos_encontrados.txt"), []byte(text.String()), 0o644); err != nil {
			return err
		}
	}
	reportJSON, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	return atomicWrite(filepath.Join(outputPath, "sync-report.json"), reportJSON, 0o644)
}

func strconvItoa(value int) string     { return strconv.Itoa(value) }
func strconvItoa64(value int64) string { return strconv.FormatInt(value, 10) }
