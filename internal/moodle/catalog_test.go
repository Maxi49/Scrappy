package moodle

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestDiscoverCombinesCoreAndActivityAttachments(t *testing.T) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if err := request.ParseForm(); err != nil {
			t.Fatal(err)
		}
		response.Header().Set("Content-Type", "application/json")
		switch request.Form.Get("wsfunction") {
		case "core_course_get_contents":
			writeJSON(t, response, []any{map[string]any{
				"id": 1, "name": "Unidad 1", "section": 1,
				"modules": []any{
					map[string]any{
						"id": 10, "name": "Ejercicios", "modname": "folder", "uservisible": 1,
						"contents": []any{
							fileItem("nodo.h", "/", serverURL(request)+"/webservice/pluginfile.php/1/nodo.h", 4),
							fileItem("nodo.h", "/Pila/", serverURL(request)+"/webservice/pluginfile.php/1/Pila/nodo.h", 4),
						},
					},
					map[string]any{
						"id": 11, "name": "Documentación", "modname": "url", "uservisible": true,
						"contents": []any{map[string]any{"type": "url", "fileurl": "https://example.com/docs"}},
					},
					map[string]any{"id": 12, "name": "Entrega", "modname": "assign", "uservisible": 1},
					map[string]any{
						"id": 13, "name": "Aviso", "modname": "label", "uservisible": 1,
						"description": `<img src="` + serverURL(request) + `/webservice/pluginfile.php/13/aviso.png">`,
					},
					map[string]any{"id": 14, "name": "Bloqueado", "modname": "resource", "uservisible": 0},
				},
			}})
		case "mod_assign_get_assignments":
			writeJSON(t, response, map[string]any{
				"courses": []any{map[string]any{
					"id": 7,
					"assignments": []any{map[string]any{
						"course": 7, "cmid": 12, "name": "Entrega",
						"introfiles": []any{fileItem("consigna.pdf", "/", serverURL(request)+"/webservice/pluginfile.php/12/consigna.pdf", 8)},
					}},
				}}, "warnings": []any{},
			})
		case "mod_label_get_labels_by_courses":
			writeJSON(t, response, map[string]any{
				"labels": []any{map[string]any{
					"course": 7, "coursemodule": 13, "name": "Aviso",
					"introfiles": []any{fileItem("aviso.png", "/", serverURL(request)+"/webservice/pluginfile.php/13/aviso.png?rev=2", 12)},
				}}, "warnings": []any{},
			})
		default:
			http.Error(response, "unexpected function", http.StatusBadRequest)
		}
	}))
	defer server.Close()

	client, err := NewClient(server.URL, "secret-token")
	if err != nil {
		t.Fatal(err)
	}
	info := SiteInfo{}
	info.Functions = append(info.Functions,
		struct {
			Name string `json:"name"`
		}{Name: "mod_assign_get_assignments"},
		struct {
			Name string `json:"name"`
		}{Name: "mod_label_get_labels_by_courses"},
	)
	catalog, err := Discover(context.Background(), client, []Course{{ID: 7, Name: "Materia", URL: server.URL}}, info, nil)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := len(catalog.Resources), 5; got != want {
		t.Fatalf("resources = %d, want %d: %#v", got, want, catalog.Resources)
	}
	if catalog.Diagnostics.ContentItemsByType["url"] != 1 {
		t.Fatalf("URL content was not counted: %#v", catalog.Diagnostics)
	}
	if catalog.Diagnostics.InaccessibleModules != 1 {
		t.Fatalf("numeric uservisible=0 was not honored: %#v", catalog.Diagnostics)
	}
	if catalog.Diagnostics.DuplicateResources != 1 {
		t.Fatalf("label image should be deduplicated: %#v", catalog.Diagnostics)
	}
	var nested, assignment bool
	for _, resource := range catalog.Resources {
		if resource.Name == "nodo.h" && resource.Subfolder == "Pila" {
			nested = true
		}
		if resource.Name == "consigna.pdf" && resource.Source == "mod_assign_get_assignments" {
			assignment = true
		}
	}
	if !nested || !assignment {
		t.Fatalf("nested=%v assignment=%v resources=%#v", nested, assignment, catalog.Resources)
	}
}

func fileItem(name, folder, rawURL string, size int64) map[string]any {
	return map[string]any{
		"type": "file", "filename": name, "filepath": folder, "fileurl": rawURL,
		"filesize": size, "mimetype": "application/octet-stream",
	}
}

func serverURL(request *http.Request) string {
	return "http://" + request.Host
}

func writeJSON(t *testing.T, response http.ResponseWriter, value any) {
	t.Helper()
	if err := json.NewEncoder(response).Encode(value); err != nil {
		t.Fatal(err)
	}
}

func TestDownloadURLAddsTokenOnlyToMoodleFileEndpoint(t *testing.T) {
	client, err := NewClient("https://moodle.example", "sensitive")
	if err != nil {
		t.Fatal(err)
	}
	internal, err := client.DownloadURL("https://moodle.example/webservice/pluginfile.php/1/file.pdf?forcedownload=1")
	if err != nil {
		t.Fatal(err)
	}
	if internal != "https://moodle.example/webservice/pluginfile.php/1/file.pdf?forcedownload=1&token=sensitive" {
		t.Fatalf("unexpected internal URL: %s", internal)
	}
	external, _ := client.DownloadURL("https://example.com/file.pdf")
	if external != "https://example.com/file.pdf" {
		t.Fatalf("token leaked to external URL: %s", external)
	}
}

func TestDownloadURLRoutesPlainPluginfileThroughWebService(t *testing.T) {
	client, err := NewClient("https://moodle.example/campus", "sensitive")
	if err != nil {
		t.Fatal(err)
	}
	got, err := client.DownloadURL("https://moodle.example/campus/pluginfile.php/13/mod_label/intro/Gu%C3%ADa%201.pdf")
	if err != nil {
		t.Fatal(err)
	}
	want := "https://moodle.example/campus/webservice/pluginfile.php/13/mod_label/intro/Gu%C3%ADa%201.pdf?token=sensitive"
	if got != want {
		t.Fatalf("got %s, want %s", got, want)
	}
}

func TestDiscoverKeepsHealthyCoursesWhenOneFails(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if err := request.ParseForm(); err != nil {
			t.Fatal(err)
		}
		if request.Form.Get("courseid") == "2" {
			http.Error(response, "boom", http.StatusForbidden)
			return
		}
		writeJSON(t, response, []any{map[string]any{
			"id": 1, "name": "Unidad", "section": 1,
			"modules": []any{map[string]any{
				"id": 10, "name": "Apunte", "modname": "resource", "uservisible": 1,
				"contents": []any{fileItem("apunte.pdf", "/", serverURL(request)+"/webservice/pluginfile.php/1/apunte.pdf", 3)},
			}},
		}})
	}))
	defer server.Close()
	client, _ := NewClient(server.URL, "token")
	catalog, err := Discover(context.Background(), client,
		[]Course{{ID: 1, Name: "Sana"}, {ID: 2, Name: "Rota"}}, SiteInfo{}, nil)
	if err != nil {
		t.Fatalf("one broken course must not abort discovery: %v", err)
	}
	if len(catalog.Resources) != 1 || catalog.Resources[0].CourseName != "Sana" {
		t.Fatalf("resources = %#v", catalog.Resources)
	}
	if len(catalog.Diagnostics.CourseErrors) != 1 || catalog.Diagnostics.CourseErrors[0].Course != "Rota" {
		t.Fatalf("course errors = %#v", catalog.Diagnostics.CourseErrors)
	}
}

func TestDiscoverFailsWhenEveryCourseFails(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		http.Error(response, "boom", http.StatusForbidden)
	}))
	defer server.Close()
	client, _ := NewClient(server.URL, "token")
	if _, err := Discover(context.Background(), client, []Course{{ID: 1, Name: "Rota"}}, SiteInfo{}, nil); err == nil {
		t.Fatal("expected an error when no course could be analysed")
	}
}

// Regression: a label linking to another activity's file produced a second
// copy of the same file (apunte.pdf + apunte_<hash>.pdf).
func TestSameMoodleFileReferencedTwiceIsCatalogedOnce(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		base := serverURL(request)
		writeJSON(t, response, []any{map[string]any{
			"id": 1, "name": "Unidad 1", "section": 1,
			"modules": []any{
				map[string]any{"id": 11, "name": "Aviso", "modname": "label", "uservisible": 1,
					"description": `Leer <a href="` + base + `/pluginfile.php/55/mod_resource/content/3/apunte.pdf">el apunte</a>`},
				map[string]any{"id": 10, "name": "Apunte", "modname": "resource", "uservisible": 1,
					"contents": []any{fileItem("apunte.pdf", "/", base+"/webservice/pluginfile.php/55/mod_resource/content/3/apunte.pdf?forcedownload=1", 4)}},
				// The resource API reports the same file with item id 0 instead of the revision.
				map[string]any{"id": 12, "name": "Otro aviso", "modname": "label", "uservisible": 1,
					"description": `<a href="` + base + `/webservice/pluginfile.php/55/mod_resource/content/0/apunte.pdf">otra vez</a>`},
				// Same filename, different Moodle file: must stay separate.
				map[string]any{"id": 13, "name": "Apunte viejo", "modname": "resource", "uservisible": 1,
					"contents": []any{fileItem("apunte.pdf", "/", base+"/webservice/pluginfile.php/56/mod_resource/content/1/apunte.pdf", 4)}},
			},
		}})
	}))
	defer server.Close()
	client, _ := NewClient(server.URL, "t")
	catalog, err := Discover(context.Background(), client, []Course{{ID: 7, Name: "M"}}, SiteInfo{}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(catalog.Resources) != 2 {
		t.Fatalf("expected 2 distinct Moodle files, got %d: %#v", len(catalog.Resources), catalog.Resources)
	}
	for _, resource := range catalog.Resources {
		if resource.CourseModule == 11 || resource.CourseModule == 12 {
			t.Fatalf("file should belong to the activity that owns it, not the label: %#v", resource)
		}
	}
}

func TestSectionSummariesContributeOnlyTheirGoogleDriveLinks(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		_ = request.ParseForm()
		if request.Form.Get("wsfunction") != "core_course_get_contents" {
			http.Error(response, "unexpected function", http.StatusBadRequest)
			return
		}
		summary := `<p>Bienvenidos <img src="` + serverURL(request) + `/webservice/pluginfile.php/1/banner.png"></p>` +
			`<p><a style="color:#fff;" href="https://drive.google.com/drive/folders/CATEDRA?usp=sharing"><span>Material de la <b>cátedra</b></span></a></p>` +
			`<p><a href="https://www.omg.org/spec/BPMN">BPMN</a></p>` +
			`<p><a title="Repaso" href="https://drive.google.com/drive/folders/CATEDRA"></a></p>`
		writeJSON(t, response, []any{
			map[string]any{"id": 1, "name": "Presentación", "section": 1, "summary": summary, "modules": []any{}},
			map[string]any{"id": 2, "name": "Unidad I", "section": 2,
				"summary": `<a href="https://drive.google.com/drive/folders/CATEDRA">otra vez</a>`, "modules": []any{}},
		})
	}))
	defer server.Close()
	client, err := NewClient(server.URL, "token")
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := Discover(context.Background(), client, []Course{{ID: 7, Name: "Sistemas"}}, SiteInfo{}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(catalog.Resources) != 1 {
		t.Fatalf("resources = %+v", catalog.Resources)
	}
	link := catalog.Resources[0]
	if link.Type != ResourceGoogle || link.Name != "Material de la cátedra" || link.ModuleName != "Presentación" || !link.Accessible {
		t.Fatalf("link = %+v", link)
	}
}
