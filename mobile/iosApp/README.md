# iosApp (stub)

This directory is a placeholder for the iOS host app (SwiftUI `App` + `ContentView` wrapping
`MainViewController()` from `composeApp`'s `iosMain`).

Per the MVP scope, iOS is design-only for now: the shared Kotlin code must **compile** for
`iosArm64` / `iosSimulatorArm64` (verified by `./gradlew :composeApp:compileKotlinIosSimulatorArm64`),
but there is no requirement to run or ship an iOS app yet. Hand-authoring a full Xcode project
`.xcodeproj` (with its generated pbxproj graph) was judged not worth the effort for a target that
isn't being run or tested in this phase.

When iOS bring-up starts, generate the real Xcode project (e.g. via the KMP wizard or by hand) with:
- A single-view SwiftUI app target named `iosApp`, bundle id `org.hitchwiki.maps`.
- `ContentView.swift` hosting `MainViewController()` via `UIViewControllerRepresentable`.
- A framework search path / direct dependency on `composeApp`'s exported `ComposeApp.framework`
  (see the `binaries.framework { baseName = "ComposeApp" }` block in
  `composeApp/build.gradle.kts`).
