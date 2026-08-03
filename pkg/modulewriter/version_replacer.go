/*
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package modulewriter

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"hpc-toolkit/pkg/logging"

	"golang.org/x/mod/semver"
)

// validateAndSanitizeVersion validates the version using golang.org/x/mod/semver.
// It handles developer dirty versions by temporarily stripping the "-dirty" suffix.
func validateAndSanitizeVersion(version string) (string, error) {
	v := version
	isDirty := false

	// Clean trailing spaces/newlines
	v = strings.TrimSpace(v)

	// Sourcing from git describe might append "-dirty"
	if strings.HasSuffix(v, "-dirty") {
		isDirty = true
		v = strings.TrimSuffix(v, "-dirty")
	}

	// semver library requires the 'v' prefix. If it's missing (e.g. if we get "1.95.0"), prepend it.
	if !strings.HasPrefix(v, "v") {
		v = "v" + v
	}

	// Validate using the official Go SemVer library
	if !semver.IsValid(v) {
		return "", fmt.Errorf("invalid semantic version string: %q", version)
	}

	// Re-append dirty suffix if it was present
	if isDirty {
		v = v + "-dirty"
	}

	return v, nil
}

// ReplaceVersionPlaceholders walks the deployment directory and replaces
// both {{VERSION}} and [VERSION] placeholders in all .tf files.
func ReplaceVersionPlaceholders(deplDir string, version string) error {
	sanitizedVersion, err := validateAndSanitizeVersion(version)
	if err != nil {
		return fmt.Errorf("failed to validate version before replacement: %w", err)
	}

	logging.Info("Staging version validation successful. Using version: %s", sanitizedVersion)

	return filepath.Walk(deplDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}
		// Only replace in .tf files
		if filepath.Ext(path) != ".tf" {
			return nil
		}

		contentBytes, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		content := string(contentBytes)

		hasPlaceholder := false
		if strings.Contains(content, "{{VERSION}}") {
			content = strings.ReplaceAll(content, "{{VERSION}}", sanitizedVersion)
			hasPlaceholder = true
		}
		if strings.Contains(content, "[VERSION]") {
			content = strings.ReplaceAll(content, "[VERSION]", sanitizedVersion)
			hasPlaceholder = true
		}

		if hasPlaceholder {
			logging.Info("Injecting version %q in: %s", sanitizedVersion, path)
			if err := os.WriteFile(path, []byte(content), info.Mode()); err != nil {
				return err
			}
		}
		return nil
	})
}
