package gdrive

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

var (
	authURL      = "https://accounts.google.com/o/oauth2/v2/auth"
	tokenURL     = "https://oauth2.googleapis.com/token"
	loginTimeout = 5 * time.Minute
)

const driveReadScope = "https://www.googleapis.com/auth/drive.readonly"
const loginScopes = "openid email " + driveReadScope

var (
	// ErrNoSession means the student never connected Google.
	ErrNoSession = errors.New("no hay una sesión de Google conectada")
	// ErrAuthExpired means Google no longer accepts the refresh token: testing
	// apps get seven-day tokens, and the student may also revoke access.
	ErrAuthExpired     = errors.New("la sesión de Google venció; reconectá Google en Conexión")
	ErrDrivePermission = errors.New("falta autorizar el permiso de lectura de Google Drive para Scrappy; reconectá Google en Conexión y aceptá ese permiso")
)

var tokenHTTP = &http.Client{Timeout: 30 * time.Second}

type LoginResult struct {
	RefreshToken string `json:"refresh_token"`
	Email        string `json:"email"`
}

type callback struct {
	code, state, failure string
}

// Login runs Google's installed-app flow: PKCE plus a loopback redirect, so no
// secret the student owns ever passes through Scrappy. openURL must show the
// consent page to the student; the core cannot open a browser on its own.
func Login(ctx context.Context, creds Credentials, openURL func(string)) (LoginResult, error) {
	if !creds.canLogin() {
		return LoginResult{}, errors.New("esta versión de Scrappy no tiene configurado el acceso a Google")
	}
	verifier, state := randomToken(32), randomToken(16)
	challenge := sha256.Sum256([]byte(verifier))

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return LoginResult{}, fmt.Errorf("abrir puerto local para Google: %w", err)
	}
	redirect := "http://" + listener.Addr().String() + "/"
	callbacks := make(chan callback, 1)
	var once sync.Once
	server := &http.Server{Handler: http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		query := r.URL.Query()
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		io.WriteString(w, `<!doctype html><meta charset="utf-8"><title>Scrappy</title>`+
			`<body style="font-family:sans-serif;text-align:center;margin-top:4em">`+
			`<h2>Listo, podés volver a Scrappy.</h2></body>`)
		once.Do(func() {
			callbacks <- callback{code: query.Get("code"), state: query.Get("state"), failure: query.Get("error")}
		})
	})}
	go server.Serve(listener)
	defer server.Close()

	consent := url.Values{
		"client_id": {creds.ClientID}, "redirect_uri": {redirect}, "response_type": {"code"},
		"scope": {loginScopes}, "state": {state}, "access_type": {"offline"}, "prompt": {"consent"},
		"code_challenge": {base64.RawURLEncoding.EncodeToString(challenge[:])}, "code_challenge_method": {"S256"},
	}
	openURL(authURL + "?" + consent.Encode())

	timer := time.NewTimer(loginTimeout)
	defer timer.Stop()
	var reply callback
	select {
	case <-ctx.Done():
		return LoginResult{}, ctx.Err()
	case <-timer.C:
		return LoginResult{}, errors.New("se agotó el tiempo para conectar Google; volvé a intentarlo")
	case reply = <-callbacks:
	}
	if reply.state != state {
		return LoginResult{}, errors.New("Google devolvió una respuesta que no corresponde a este inicio de sesión")
	}
	switch {
	case reply.failure == "admin_policy_enforced" || reply.failure == "org_internal":
		return LoginResult{}, errors.New("el administrador de la cuenta de Google (UCC) bloquea esta aplicación")
	case reply.failure != "":
		return LoginResult{}, fmt.Errorf("Google rechazó el acceso (%s)", reply.failure)
	case reply.code == "":
		return LoginResult{}, errors.New("Google no devolvió un código de acceso")
	}

	tokens, err := requestToken(ctx, creds, url.Values{
		"grant_type": {"authorization_code"}, "code": {reply.code},
		"code_verifier": {verifier}, "redirect_uri": {redirect},
	})
	if err != nil {
		return LoginResult{}, err
	}
	if tokens.RefreshToken == "" {
		return LoginResult{}, errors.New("Google no entregó una sesión permanente; volvé a intentarlo")
	}
	return LoginResult{RefreshToken: tokens.RefreshToken, Email: emailFromIDToken(tokens.IDToken)}, nil
}

type tokenResponse struct {
	AccessToken  string  `json:"access_token"`
	ExpiresIn    int     `json:"expires_in"`
	RefreshToken string  `json:"refresh_token"`
	IDToken      string  `json:"id_token"`
	Error        string  `json:"error"`
	Scope        *string `json:"scope"`
}

func (t tokenResponse) permitsDriveRead() bool {
	// OAuth can omit scope when it is unchanged. An explicitly returned
	// grant must allow reading file contents, not just metadata or identity.
	if t.Scope == nil {
		return true
	}
	for _, scope := range strings.Fields(*t.Scope) {
		if scope == driveReadScope || scope == "https://www.googleapis.com/auth/drive" {
			return true
		}
	}
	return false
}

type tokenError struct {
	status int
	code   string
}

func (e *tokenError) Error() string {
	if e.code != "" {
		return fmt.Sprintf("Google rechazó la sesión (%s)", e.code)
	}
	return fmt.Sprintf("Google respondió HTTP %d al validar la sesión", e.status)
}

// requestToken posts to Google's token endpoint. Errors carry only the status
// and Google's error code, never the form, which holds the secrets.
func requestToken(ctx context.Context, creds Credentials, form url.Values) (tokenResponse, error) {
	form.Set("client_id", creds.ClientID)
	form.Set("client_secret", creds.ClientSecret)
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, tokenURL, strings.NewReader(form.Encode()))
	if err != nil {
		return tokenResponse{}, err
	}
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := tokenHTTP.Do(request)
	if err != nil {
		if ctx.Err() != nil {
			return tokenResponse{}, ctx.Err()
		}
		return tokenResponse{}, errors.New("no se pudo contactar a Google")
	}
	defer response.Body.Close()
	var tokens tokenResponse
	decodeErr := json.NewDecoder(io.LimitReader(response.Body, 1<<20)).Decode(&tokens)
	if response.StatusCode != http.StatusOK || tokens.Error != "" {
		return tokenResponse{}, &tokenError{status: response.StatusCode, code: tokens.Error}
	}
	if decodeErr != nil || tokens.AccessToken == "" {
		return tokenResponse{}, errors.New("Google devolvió una respuesta inválida")
	}
	if !tokens.permitsDriveRead() {
		return tokenResponse{}, ErrDrivePermission
	}
	return tokens, nil
}

// emailFromIDToken reads the email claim. The token comes straight from
// Google over TLS and only labels the session in the UI, so the signature is
// not verified.
func emailFromIDToken(token string) string {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return ""
	}
	payload, err := base64.RawURLEncoding.DecodeString(strings.TrimRight(parts[1], "="))
	if err != nil {
		return ""
	}
	var claims struct {
		Email string `json:"email"`
	}
	if json.Unmarshal(payload, &claims) != nil {
		return ""
	}
	return claims.Email
}

func randomToken(size int) string {
	buffer := make([]byte, size)
	if _, err := rand.Read(buffer); err != nil {
		panic(err)
	}
	return base64.RawURLEncoding.EncodeToString(buffer)
}

// TokenSource turns the stored refresh token into access tokens on demand and
// is safe for the download workers to share.
type TokenSource struct {
	creds   Credentials
	refresh string

	mu      sync.Mutex
	access  string
	expiry  time.Time
	expired bool
}

func NewTokenSource(creds Credentials, refreshToken string) *TokenSource {
	return &TokenSource{creds: creds, refresh: strings.TrimSpace(refreshToken)}
}

// HasSession reports whether a refresh token was supplied at all.
func (s *TokenSource) HasSession() bool { return s != nil && s.refresh != "" }

// Expired reports whether Google rejected the refresh token during this run.
func (s *TokenSource) Expired() bool {
	if s == nil {
		return false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.expired
}

func (s *TokenSource) Token(ctx context.Context) (string, error) {
	if !s.HasSession() {
		return "", ErrNoSession
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.expired {
		return "", ErrAuthExpired
	}
	if s.access != "" && time.Until(s.expiry) > time.Minute {
		return s.access, nil
	}
	tokens, err := requestToken(ctx, s.creds, url.Values{"grant_type": {"refresh_token"}, "refresh_token": {s.refresh}})
	if err != nil {
		var rejected *tokenError
		if errors.As(err, &rejected) && rejected.code == "invalid_grant" {
			s.expired = true
			return "", ErrAuthExpired
		}
		return "", err
	}
	s.access = tokens.AccessToken
	s.expiry = time.Now().Add(time.Duration(tokens.ExpiresIn) * time.Second)
	return s.access, nil
}
