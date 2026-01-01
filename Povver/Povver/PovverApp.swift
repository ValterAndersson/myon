//
//  PovverApp.swift
//  Povver
//
//  Created by Valter Andersson on 9.6.2025.
//

import SwiftUI

@main
struct PovverApp: App {
    init() {
        FirebaseConfig.shared.configure()
    }
    
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
