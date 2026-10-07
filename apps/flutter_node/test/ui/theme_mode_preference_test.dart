import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sound_detector_clean/ui/theme/theme_mode_preference.dart';

void main() {
  test('theme mode defaults to dark when no preference exists', () async {
    SharedPreferences.setMockInitialValues({});

    expect(await ThemeModePreference.load(), ThemeMode.dark);
    expect(ThemeModePreference.decode(null), ThemeMode.dark);
  });

  test('theme mode selection persists across preference reloads', () async {
    SharedPreferences.setMockInitialValues({});

    await ThemeModePreference.save(ThemeMode.system);
    expect(await ThemeModePreference.load(), ThemeMode.system);

    await ThemeModePreference.save(ThemeMode.light);
    expect(await ThemeModePreference.load(), ThemeMode.light);

    await ThemeModePreference.save(ThemeMode.dark);
    expect(await ThemeModePreference.load(), ThemeMode.dark);
  });
}
