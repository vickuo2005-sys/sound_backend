import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

abstract final class ThemeModePreference {
  static const String preferenceKey = 'theme_mode';

  static Future<ThemeMode> load() async {
    final preferences = await SharedPreferences.getInstance();
    return decode(preferences.getString(preferenceKey));
  }

  static Future<void> save(ThemeMode mode) async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.setString(preferenceKey, encode(mode));
  }

  static ThemeMode decode(String? value) {
    return switch (value) {
      'system' => ThemeMode.system,
      'light' => ThemeMode.light,
      _ => ThemeMode.dark,
    };
  }

  static String encode(ThemeMode mode) {
    return switch (mode) {
      ThemeMode.system => 'system',
      ThemeMode.light => 'light',
      ThemeMode.dark => 'dark',
    };
  }
}
