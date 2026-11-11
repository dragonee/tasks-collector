import SwiftUI

/// The four screens of the app, a tab each.
struct RootView: View {

    let services: AppServices

    var body: some View {
        TabView {
            TodayView(model: services.today, addPhoto: services.addPhoto, services: services)
                .tabItem { Label("Today", systemImage: "checklist") }
            TripsView(model: services.trips, services: services)
                .tabItem { Label("Trips", systemImage: "map") }
            HealthView(model: services.main, settings: services.settings)
                .tabItem { Label("Health", systemImage: "heart") }
            SettingsView(model: services.main, settings: services.settings)
                .tabItem { Label("Settings", systemImage: "gearshape") }
        }
        // A standalone photo has no screen showing how its upload went, so
        // that is said here, over whichever screen is in view.
        .overlay(alignment: .bottom) {
            if let notice = services.addPhoto.notice {
                Text(notice)
                    .font(.footnote)
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.black.opacity(0.8), in: Capsule())
                    .padding(.bottom, 64)
                    .transition(.opacity)
            }
        }
        .animation(.default, value: services.addPhoto.notice)
    }
}

/// An error across the top of a screen, with a way to put it away.
struct ErrorBanner: View {
    let message: String
    let onDismiss: () -> Void

    var body: some View {
        HStack {
            Text(message)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button("Dismiss", action: onDismiss)
        }
        .font(.footnote)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.red.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
    }
}

/// A text field of several lines for a sheet, with the placeholder the
/// single-line ones have.
struct NoteField: View {
    let placeholder: String
    @Binding var text: String
    var lines = 3

    var body: some View {
        TextField(placeholder, text: $text, axis: .vertical)
            .lineLimit(lines...8)
    }
}

/// "1 change", "3 changes".
func counted(_ count: Int, _ one: String, _ many: String) -> String {
    count == 1 ? "\(count) \(one)" : "\(count) \(many)"
}
