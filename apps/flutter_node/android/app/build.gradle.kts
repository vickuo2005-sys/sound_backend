import java.io.File
import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

val keystoreProperties = Properties()
val keystorePropertiesFile = rootProject.file("key.properties")
val hasReleaseSigningFile = keystorePropertiesFile.exists()
if (hasReleaseSigningFile) {
    keystoreProperties.load(FileInputStream(keystorePropertiesFile))
}
val requiredReleaseSigningKeys = listOf("storeFile", "storePassword", "keyAlias", "keyPassword")
val releaseSigningComplete = hasReleaseSigningFile &&
    requiredReleaseSigningKeys.all { key ->
        (keystoreProperties[key] as String?)?.isNotBlank() == true
    }
val requireReleaseSigning =
    providers.gradleProperty("REQUIRE_RELEASE_SIGNING").orNull == "true" ||
        providers.gradleProperty("requireReleaseSigning").orNull == "true"
if (hasReleaseSigningFile && !releaseSigningComplete) {
    throw GradleException(
        "android/key.properties is incomplete. Required keys: ${requiredReleaseSigningKeys.joinToString(", ")}"
    )
}
if (requireReleaseSigning && !releaseSigningComplete) {
    throw GradleException(
        "Production release signing is required, but android/key.properties or keystore is missing."
    )
}

android {
    namespace = "com.example.sound_detector_clean"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.sound_detector_clean"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["appLabel"] = "Sound Detector Node"
    }

    signingConfigs {
        create("release") {
            if (releaseSigningComplete) {
                val storeFilePath = keystoreProperties["storeFile"] as String
                val candidate = File(storeFilePath)
                storeFile = if (candidate.isAbsolute) {
                    candidate
                } else {
                    rootProject.file(storeFilePath)
                }
                storePassword = keystoreProperties["storePassword"] as String
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
            }
        }
    }

    flavorDimensions += "environment"
    productFlavors {
        create("staging") {
            dimension = "environment"
            applicationIdSuffix = ".staging"
            versionNameSuffix = "-staging"
            manifestPlaceholders["appLabel"] = "Sound Detector Node Staging"
        }
        create("production") {
            dimension = "environment"
            manifestPlaceholders["appLabel"] = "Sound Detector Node"
        }
    }

    buildTypes {
        release {
            signingConfig = if (releaseSigningComplete) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

flutter {
    source = "../.."
}
