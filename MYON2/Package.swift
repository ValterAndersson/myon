// swift-tools-version:5.5
import PackageDescription

let package = Package(
    name: "MYON2",
    platforms: [
        .iOS(.v15),
        .macOS(.v12)
    ],
    products: [
        .library(
            name: "MYON2",
            targets: ["MYON2"]),
    ],
    dependencies: [
        .package(url: "https://github.com/firebase/firebase-ios-sdk.git", from: "10.0.0"),
    ],
    targets: [
        .target(
            name: "MYON2",
            dependencies: [
                .product(name: "FirebaseFirestore", package: "firebase-ios-sdk"),
                .product(name: "FirebaseFirestoreSwift", package: "firebase-ios-sdk"),
                .product(name: "FirebaseAuth", package: "firebase-ios-sdk"),
                .product(name: "FirebaseCore", package: "firebase-ios-sdk"),
                .product(name: "FirebaseMessaging", package: "firebase-ios-sdk"),
            ],
            linkerSettings: [
                .linkedFramework("Foundation"),
                .linkedFramework("UIKit"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("QuartzCore"),
                .linkedFramework("SystemConfiguration"),
                .linkedFramework("Security"),
                .linkedFramework("CFNetwork"),
                .linkedFramework("CoreTelephony"),
                .linkedFramework("CoreFoundation"),
                .linkedFramework("CoreServices"),
                .linkedFramework("CoreData"),
                .linkedFramework("CoreLocation"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("CoreVideo"),
                .linkedFramework("CoreAudio"),
                .linkedFramework("CoreImage"),
                .linkedFramework("CoreText"),
                .linkedFramework("CoreML"),
                .linkedFramework("CoreSpotlight"),
                .linkedFramework("CoreBluetooth"),
                .linkedFramework("CoreNFC"),
                .linkedFramework("CoreMotion"),
                .linkedFramework("CoreHaptics"),
                .linkedFramework("CoreAnimation"),
                .linkedFramework("CoreImage"),
                .linkedFramework("CoreText"),
                .linkedFramework("CoreVideo"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("CoreAudio"),
                .linkedFramework("CoreLocation"),
                .linkedFramework("CoreBluetooth"),
                .linkedFramework("CoreMotion"),
                .linkedFramework("CoreHaptics"),
                .linkedFramework("CoreNFC"),
                .linkedFramework("CoreSpotlight"),
                .linkedFramework("CoreML"),
                .linkedFramework("CoreData"),
                .linkedFramework("CoreServices"),
                .linkedFramework("CoreFoundation"),
                .linkedFramework("CFNetwork"),
                .linkedFramework("Security"),
                .linkedFramework("SystemConfiguration"),
                .linkedFramework("QuartzCore"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("UIKit"),
                .linkedFramework("Foundation")
            ]),
        .testTarget(
            name: "MYON2Tests",
            dependencies: ["MYON2"]),
    ]
) 