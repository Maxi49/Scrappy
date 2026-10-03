package gdrive

import "os"

// Set at build time with -ldflags "-X github.com/Maxi49/Scrappy/internal/gdrive.apiKey=…".
// Google documents that a desktop OAuth client cannot keep its secret; it stays
// out of the repository only so it is not trivially reused.
var (
	apiKey       string
	clientID     string
	clientSecret string
)

// Credentials identify Scrappy to Google, not the student.
type Credentials struct {
	APIKey       string
	ClientID     string
	ClientSecret string
}

// AppCredentials returns the build-time credentials, falling back to the
// SCRAPPY_GOOGLE_* environment variables for development builds.
func AppCredentials() Credentials {
	pick := func(built, env string) string {
		if built != "" {
			return built
		}
		return os.Getenv(env)
	}
	return Credentials{
		APIKey:       pick(apiKey, "SCRAPPY_GOOGLE_API_KEY"),
		ClientID:     pick(clientID, "SCRAPPY_GOOGLE_CLIENT_ID"),
		ClientSecret: pick(clientSecret, "SCRAPPY_GOOGLE_CLIENT_SECRET"),
	}
}

func (c Credentials) canLogin() bool { return c.ClientID != "" && c.ClientSecret != "" }
