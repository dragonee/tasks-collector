import SwiftUI

/// Which server the app talks to, and as whom. "Log in" opens the server in
/// a browser sheet, where the user logs in as they do on the web; the phone
/// comes back with a token of its own (see `OAuthLogin`). A token can still
/// be pasted in instead.
struct SettingsView: View {

    let model: MainModel
    let settings: Settings

    @State private var url = ""
    @State private var token = ""

    var body: some View {
        let snapshot = settings.snapshot
        NavigationStack {
            Form {
                Section {
                    TextField("https://tasks.example.com", text: $url)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Log in") { Task { await model.login(serverUrl: url) } }
                        .disabled(url.trimmingCharacters(in: .whitespaces).isEmpty || model.loginBusy)
                    if snapshot.isConfigured {
                        Button("Log out", role: .destructive) { Task { await model.logout() } }
                            .disabled(model.loginBusy)
                    }
                } header: {
                    Text("Server URL")
                } footer: {
                    status(snapshot)
                }

                Section("API token (instead of logging in)") {
                    SecureField("Token", text: $token)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Save") { model.save(serverUrl: url, apiToken: token) }
                        .disabled(
                            url.trimmingCharacters(in: .whitespaces).isEmpty
                                || token.trimmingCharacters(in: .whitespaces).isEmpty
                        )
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
        }
        .onChange(of: snapshot.serverUrl, initial: true) { _, saved in
            if url.isEmpty { url = saved }
        }
        // The token changes under the field when the phone logs in or out;
        // what the field holds must not be an old one that Save would put
        // back.
        .onChange(of: snapshot.apiToken, initial: true) { _, saved in
            token = saved
        }
    }

    @ViewBuilder
    private func status(_ snapshot: SettingsSnapshot) -> some View {
        if model.loginBusy {
            Text("Talking to the server…")
        } else if let error = model.loginError {
            Text("That didn't work: \(error)").foregroundStyle(.red)
        } else if snapshot.isConfigured {
            Text("This phone is logged in to \(snapshot.serverUrl).")
        } else {
            Text("Opens the server in your browser. You log in there as usual, and this phone gets a token of its own. You can log it out again in your account settings on the web.")
        }
    }
}
