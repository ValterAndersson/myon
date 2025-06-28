//
//  MYON2App.swift
//  MYON2
//
//  Created by Valter Andersson on 9.6.2025.
//

import SwiftUI

@main
struct MYON2App: App {
    init() {
        FirebaseConfig.shared.configure()
    }
    
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}
