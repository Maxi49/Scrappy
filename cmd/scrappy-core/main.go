package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"strings"
	"sync"

	"github.com/Maxi49/Scrappy/internal/moodle"
	"github.com/Maxi49/Scrappy/internal/syncer"
)

type request struct {
	Action     string          `json:"action"`
	BaseURL    string          `json:"base_url"`
	Username   string          `json:"username"`
	Password   string          `json:"password"`
	Token      string          `json:"token"`
	OutputPath string          `json:"output_path"`
	Export     *bool           `json:"export"`
	Courses    []courseRequest `json:"courses"`
}

type courseRequest struct {
	ID           int    `json:"id"`
	Name         string `json:"name"`
	URL          string `json:"url"`
	Mode         string `json:"mode"`
	ScanExisting bool   `json:"scan_existing"`
}

type emitter struct {
	mu      sync.Mutex
	encoder *json.Encoder
}

var errResultAlreadySent = errors.New("result already sent")

func (e *emitter) send(value any) {
	e.mu.Lock()
	defer e.mu.Unlock()
	_ = e.encoder.Encode(value)
}

func (e *emitter) progress(message string) {
	e.send(map[string]any{"event": "progress", "message": message})
}

func main() {
	if len(os.Args) > 1 && (os.Args[1] == "--version" || os.Args[1] == "version") {
		fmt.Println("scrappy-core 2.0.0 " + runtime.GOOS + "/" + runtime.GOARCH)
		return
	}
	if len(os.Args) > 1 && (os.Args[1] == "--help" || os.Args[1] == "-h") {
		fmt.Println("Scrappy Go core. Requests are newline-delimited JSON on stdin.")
		return
	}

	out := &emitter{encoder: json.NewEncoder(os.Stdout)}
	decoder := json.NewDecoder(bufio.NewReader(os.Stdin))
	var input request
	if err := decoder.Decode(&input); err != nil {
		out.send(map[string]any{"event": "result", "ok": false, "error": "solicitud JSON inválida"})
		os.Exit(2)
	}
	if err := run(context.Background(), input, out); err != nil {
		if errors.Is(err, errResultAlreadySent) {
			os.Exit(1)
		}
		out.send(map[string]any{"event": "result", "ok": false, "error": err.Error()})
		os.Exit(1)
	}
}

func run(ctx context.Context, input request, out *emitter) error {
	baseURL := strings.TrimSpace(input.BaseURL)
	if baseURL == "" {
		baseURL = "https://presencial.ucc.edu.ar"
	}
	client, err := moodle.NewClient(baseURL, input.Token)
	if err != nil {
		return err
	}

	switch input.Action {
	case "courses":
		out.progress("Autenticando con Moodle...")
		courses, info, err := moodle.ListCourses(ctx, client, input.Username, input.Password)
		if err != nil {
			return err
		}
		out.send(map[string]any{
			"event": "result", "ok": true, "token": client.Token(),
			"courses": courses, "available_functions": len(info.Functions),
		})
		return nil

	case "sync", "diagnose":
		info, err := authenticateAndInfo(ctx, client, input.Username, input.Password)
		if err != nil {
			return err
		}
		courses, modes, err := requestedCourses(input.Courses)
		if err != nil {
			return err
		}
		out.progress(fmt.Sprintf("Analizando %d materia(s) vía API...", len(courses)))
		catalog, err := moodle.Discover(ctx, client, courses, info, out.progress)
		if err != nil {
			return err
		}
		out.progress(fmt.Sprintf(
			"API analizada: %d actividades, %d recursos únicos, %d módulos inaccesibles.",
			catalog.Diagnostics.Activities, len(catalog.Resources), catalog.Diagnostics.InaccessibleModules,
		))
		if input.Action == "diagnose" {
			out.send(map[string]any{
				"event": "result", "ok": true, "resource_count": len(catalog.Resources),
				"diagnostics": catalog.Diagnostics,
			})
			return nil
		}
		report, syncErr := syncer.Run(ctx, client, catalog, syncer.Options{
			OutputPath: input.OutputPath, Modes: modes, Progress: out.progress,
			WriteIndexes: input.Export == nil || *input.Export,
		})
		if syncErr != nil {
			out.send(map[string]any{"event": "result", "ok": false, "error": syncErr.Error(), "report": report})
			return errResultAlreadySent
		}
		out.send(map[string]any{"event": "result", "ok": true, "report": report})
		return nil
	default:
		return errors.New("acción desconocida; usar courses, diagnose o sync")
	}
}

func authenticateAndInfo(ctx context.Context, client *moodle.Client, username, password string) (moodle.SiteInfo, error) {
	if client.Token() == "" {
		if err := client.Authenticate(ctx, username, password); err != nil {
			return moodle.SiteInfo{}, err
		}
	}
	info, err := client.SiteInfo(ctx)
	if err == nil {
		return info, nil
	}
	// A token can expire between course selection and download. If the UI kept
	// credentials in memory, refresh once without exposing either value.
	if username == "" || password == "" {
		return moodle.SiteInfo{}, err
	}
	if authErr := client.Authenticate(ctx, username, password); authErr != nil {
		return moodle.SiteInfo{}, err
	}
	return client.SiteInfo(ctx)
}

func requestedCourses(input []courseRequest) ([]moodle.Course, map[int]syncer.Mode, error) {
	if len(input) == 0 {
		return nil, nil, errors.New("no se seleccionaron materias")
	}
	courses := make([]moodle.Course, 0, len(input))
	modes := make(map[int]syncer.Mode, len(input))
	seen := make(map[int]bool)
	for _, item := range input {
		if item.ID <= 0 {
			return nil, nil, fmt.Errorf("ID de materia inválido: %s", strconv.Itoa(item.ID))
		}
		if seen[item.ID] {
			continue
		}
		seen[item.ID] = true
		courses = append(courses, moodle.Course{ID: item.ID, Name: strings.TrimSpace(item.Name), URL: item.URL})
		mode := item.Mode
		if mode != "full" && mode != "update" {
			mode = "update"
		}
		modes[item.ID] = syncer.Mode{Name: mode, ScanExisting: item.ScanExisting}
	}
	return courses, modes, nil
}
