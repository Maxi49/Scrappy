package gdrive

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

var testCreds = Credentials{APIKey: "KEY", ClientID: "CID", ClientSecret: "CSECRET"}

func fakeIDToken(email string) string {
	payload, _ := json.Marshal(map[string]string{"email": email})
	return "e30." + base64.RawURLEncoding.EncodeToString(payload) + ".sig"
}

// fakeTokenServer validates the PKCE exchange and refresh grants like Google.
func fakeTokenServer(t *testing.T, refreshStatus *atomic.Int32) *httptest.Server {
	t.Helper()
	challenges := map[string]string{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := r.ParseForm(); err != nil {
			t.Fatal(err)
		}
		if r.Form.Get("client_id") != "CID" || r.Form.Get("client_secret") != "CSECRET" {
			http.Error(w, `{"error":"invalid_client"}`, http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		switch r.Form.Get("grant_type") {
		case "authorization_code":
			sum := sha256.Sum256([]byte(r.Form.Get("code_verifier")))
			if r.Form.Get("code") != "GOODCODE" || challenges["GOODCODE"] != base64.RawURLEncoding.EncodeToString(sum[:]) {
				w.WriteHeader(http.StatusBadRequest)
				w.Write([]byte(`{"error":"invalid_grant"}`))
				return
			}
			json.NewEncoder(w).Encode(map[string]any{
				"access_token": "AT1", "expires_in": 3600, "refresh_token": "RT1",
				"id_token": fakeIDToken("alumno@ucc.edu.ar"),
			})
		case "refresh_token":
			if refreshStatus != nil && refreshStatus.Load() != 0 {
				w.WriteHeader(int(refreshStatus.Load()))
				w.Write([]byte(`{"error":"invalid_grant","error_description":"Token has been expired or revoked."}`))
				return
			}
			if r.Form.Get("refresh_token") != "RT1" {
				w.WriteHeader(http.StatusBadRequest)
				w.Write([]byte(`{"error":"invalid_grant"}`))
				return
			}
			json.NewEncoder(w).Encode(map[string]any{"access_token": "AT2", "expires_in": 3600})
		}
	}))
	originalToken, originalAuth := tokenURL, authURL
	tokenURL = server.URL + "/token"
	authURL = server.URL + "/auth"
	// The authorize step happens in the browser; tests record the challenge
	// the way Google would when the user consents.
	recordChallenge = func(code, challenge string) { challenges[code] = challenge }
	t.Cleanup(func() {
		server.Close()
		tokenURL, authURL = originalToken, originalAuth
		recordChallenge = func(string, string) {}
	})
	return server
}

var recordChallenge = func(string, string) {}

// browser plays the user: it reads the consent URL and hits the loopback
// redirect with the given query.
func browser(t *testing.T, query func(state string) url.Values) func(string) {
	return func(raw string) {
		consent, err := url.Parse(raw)
		if err != nil {
			t.Error(err)
			return
		}
		values := consent.Query()
		for _, required := range []string{"client_id", "redirect_uri", "state", "code_challenge"} {
			if values.Get(required) == "" {
				t.Errorf("consent URL lacks %s: %s", required, raw)
			}
		}
		if values.Get("code_challenge_method") != "S256" || values.Get("access_type") != "offline" {
			t.Errorf("consent URL lacks PKCE/offline: %s", raw)
		}
		if !strings.Contains(values.Get("scope"), "drive.readonly") {
			t.Errorf("scope = %q", values.Get("scope"))
		}
		recordChallenge("GOODCODE", values.Get("code_challenge"))
		go func() {
			response, err := http.Get(values.Get("redirect_uri") + "?" + query(values.Get("state")).Encode())
			if err == nil {
				response.Body.Close()
			}
		}()
	}
}

func TestLoginReturnsRefreshTokenAndEmail(t *testing.T) {
	fakeTokenServer(t, nil)
	result, err := Login(context.Background(), testCreds, browser(t, func(state string) url.Values {
		return url.Values{"code": {"GOODCODE"}, "state": {state}}
	}))
	if err != nil {
		t.Fatal(err)
	}
	if result.RefreshToken != "RT1" || result.Email != "alumno@ucc.edu.ar" {
		t.Fatalf("result = %+v", result)
	}
}

func TestGoogleSessionChecksGrantedDriveScope(t *testing.T) {
	for _, test := range []struct {
		name    string
		scope   any
		allowed bool
	}{
		{"identity only", "openid email", false},
		{"metadata only", "https://www.googleapis.com/auth/drive.metadata.readonly", false},
		{"individual files only", "https://www.googleapis.com/auth/drive.file", false},
		{"empty grant", "", false},
		{"readonly", loginScopes, true},
		{"full drive", "openid https://www.googleapis.com/auth/drive", true},
		// OAuth permits omitting scope when it is unchanged from the request.
		{"omitted", nil, true},
	} {
		t.Run(test.name, func(t *testing.T) {
			fakeTokenServer(t, nil)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				payload := map[string]any{"access_token": "AT2", "expires_in": 3600, "refresh_token": "RT1"}
				if test.scope != nil {
					payload["scope"] = test.scope
				}
				json.NewEncoder(w).Encode(payload)
			}))
			defer server.Close()
			tokenURL = server.URL
			result, err := Login(context.Background(), testCreds, browser(t, func(state string) url.Values {
				return url.Values{"code": {"GOODCODE"}, "state": {state}}
			}))
			if (err == nil) != test.allowed {
				t.Fatalf("login allowed = %v, want %v: %v", err == nil, test.allowed, err)
			}
			if !test.allowed && (result.RefreshToken != "" || !strings.Contains(err.Error(), "permiso")) {
				t.Fatalf("login accepted partial consent or omitted guidance: %+v, %v", result, err)
			}
			source := NewTokenSource(testCreds, "RT1")
			token, err := source.Token(context.Background())
			if (err == nil) != test.allowed || (!test.allowed && token != "") {
				t.Fatalf("refresh allowed = %v, want %v: %v", err == nil, test.allowed, err)
			}
		})
	}
}

func TestLoginRejectsForeignState(t *testing.T) {
	fakeTokenServer(t, nil)
	_, err := Login(context.Background(), testCreds, browser(t, func(string) url.Values {
		return url.Values{"code": {"GOODCODE"}, "state": {"forged"}}
	}))
	if err == nil {
		t.Fatal("login accepted a callback with a foreign state")
	}
}

func TestLoginExplainsGoogleRefusal(t *testing.T) {
	fakeTokenServer(t, nil)
	_, err := Login(context.Background(), testCreds, browser(t, func(state string) url.Values {
		return url.Values{"error": {"admin_policy_enforced"}, "state": {state}}
	}))
	if err == nil || !strings.Contains(err.Error(), "administrador") {
		t.Fatalf("err = %v", err)
	}
	_, err = Login(context.Background(), testCreds, browser(t, func(state string) url.Values {
		return url.Values{"error": {"access_denied"}, "state": {state}}
	}))
	if err == nil || !strings.Contains(err.Error(), "rechaz") {
		t.Fatalf("err = %v", err)
	}
}

func TestLoginStopsWhenCancelled(t *testing.T) {
	fakeTokenServer(t, nil)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := Login(ctx, testCreds, func(string) {})
		done <- err
	}()
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("err = %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("login did not stop after cancellation")
	}
}

func TestLoginTimesOut(t *testing.T) {
	fakeTokenServer(t, nil)
	original := loginTimeout
	loginTimeout = 50 * time.Millisecond
	t.Cleanup(func() { loginTimeout = original })
	_, err := Login(context.Background(), testCreds, func(string) {})
	if err == nil || !strings.Contains(err.Error(), "tiempo") {
		t.Fatalf("err = %v", err)
	}
}

func TestLoginRequiresCredentials(t *testing.T) {
	_, err := Login(context.Background(), Credentials{}, func(string) {})
	if err == nil {
		t.Fatal("login ran without OAuth client credentials")
	}
}

func TestTokenSourceRefreshesOnceAndCaches(t *testing.T) {
	fakeTokenServer(t, nil)
	source := NewTokenSource(testCreds, "RT1")
	for i := 0; i < 3; i++ {
		token, err := source.Token(context.Background())
		if err != nil || token != "AT2" {
			t.Fatalf("token = %q, %v", token, err)
		}
	}
	if source.Expired() {
		t.Fatal("valid session reported as expired")
	}
}

func TestTokenSourceReportsExpiredSession(t *testing.T) {
	status := &atomic.Int32{}
	status.Store(http.StatusBadRequest)
	fakeTokenServer(t, status)
	source := NewTokenSource(testCreds, "RT1")
	_, err := source.Token(context.Background())
	if !errors.Is(err, ErrAuthExpired) || !source.Expired() {
		t.Fatalf("err = %v, expired = %v", err, source.Expired())
	}
	if strings.Contains(err.Error(), "RT1") {
		t.Fatal("refresh token leaked into the error")
	}
}

func TestTokenSourceWithoutRefreshToken(t *testing.T) {
	source := NewTokenSource(testCreds, "")
	if _, err := source.Token(context.Background()); !errors.Is(err, ErrNoSession) {
		t.Fatalf("err = %v", err)
	}
}
