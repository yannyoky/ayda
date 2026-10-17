import Shared
import SwiftUI

/// Placeholder start screen; the real screens follow the Android ones (#100).
struct ContentView: View {
    private let palette = Palettes.shared.Graphite

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Айда!")
                .font(.system(size: 44, weight: .heavy))
                .foregroundStyle(Color(argb: palette.accent))
            Text("Квесты дня")
                .font(.title3.bold())
                .foregroundStyle(Color(argb: palette.onPlate))
        }
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(argb: palette.plate), in: RoundedRectangle(cornerRadius: CGFloat(Radii.shared.CARD)))
        .padding(16)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Color(argb: palette.bg))
    }
}

extension Color {
    /// Colour tokens from the shared module are ARGB longs.
    init(argb: Int64) {
        self.init(
            .sRGB,
            red: Double((argb >> 16) & 0xFF) / 255,
            green: Double((argb >> 8) & 0xFF) / 255,
            blue: Double(argb & 0xFF) / 255,
            opacity: Double((argb >> 24) & 0xFF) / 255
        )
    }
}
