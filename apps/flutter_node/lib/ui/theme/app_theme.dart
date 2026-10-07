import 'package:flutter/material.dart';

abstract final class AppTheme {
  static ThemeData get light => _build(
    ColorScheme.fromSeed(
      seedColor: const Color(0xFF0F766E),
      brightness: Brightness.light,
      surface: const Color(0xFFF4F7FA),
    ).copyWith(
      surfaceContainerLowest: const Color(0xFFFFFFFF),
      surfaceContainerLow: const Color(0xFFF8FAFC),
      surfaceContainer: const Color(0xFFEEF2F6),
      surfaceContainerHigh: const Color(0xFFE6EBF1),
      outline: const Color(0xFF8B9AAF),
      outlineVariant: const Color(0xFFD6DEE8),
    ),
  );

  static ThemeData get dark => _build(
    const ColorScheme.dark(
      primary: Color(0xFF5EEAD4),
      onPrimary: Color(0xFF062E2B),
      primaryContainer: Color(0xFF143B3A),
      onPrimaryContainer: Color(0xFF99F6E4),
      secondary: Color(0xFF60A5FA),
      onSecondary: Color(0xFF071E33),
      secondaryContainer: Color(0xFF173452),
      onSecondaryContainer: Color(0xFFBFDBFE),
      tertiary: Color(0xFFC4B5FD),
      onTertiary: Color(0xFF271B4B),
      tertiaryContainer: Color(0xFF352A5C),
      onTertiaryContainer: Color(0xFFEDE9FE),
      error: Color(0xFFFB7185),
      onError: Color(0xFF430914),
      errorContainer: Color(0xFF4A1723),
      onErrorContainer: Color(0xFFFFD9DF),
      surface: Color(0xFF0B1220),
      onSurface: Color(0xFFE5ECF5),
      onSurfaceVariant: Color(0xFF9EACC0),
      surfaceContainerLowest: Color(0xFF08101C),
      surfaceContainerLow: Color(0xFF101A2A),
      surfaceContainer: Color(0xFF142033),
      surfaceContainerHigh: Color(0xFF1A2940),
      surfaceContainerHighest: Color(0xFF22334A),
      outline: Color(0xFF496078),
      outlineVariant: Color(0xFF27384F),
    ),
  );

  static ThemeData _build(ColorScheme colorScheme) {
    final isDark = colorScheme.brightness == Brightness.dark;

    return ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: colorScheme.surface,
      visualDensity: VisualDensity.compact,
      textTheme: const TextTheme(
        headlineMedium: TextStyle(fontSize: 38, fontWeight: FontWeight.w700),
        headlineSmall: TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
        titleLarge: TextStyle(fontSize: 19, fontWeight: FontWeight.w700),
        titleMedium: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        bodyLarge: TextStyle(fontSize: 15),
        bodyMedium: TextStyle(fontSize: 14),
        bodySmall: TextStyle(fontSize: 12),
        labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
      ),
      appBarTheme: AppBarTheme(
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        toolbarHeight: 54,
        backgroundColor: colorScheme.surface,
        foregroundColor: colorScheme.onSurface,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: TextStyle(
          color: colorScheme.onSurface,
          fontSize: 20,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.2,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: colorScheme.surfaceContainer,
        surfaceTintColor: Colors.transparent,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: colorScheme.outlineVariant),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colorScheme.surfaceContainerLow,
        isDense: true,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colorScheme.outlineVariant),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: colorScheme.outlineVariant),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 12,
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 68,
        backgroundColor: isDark
            ? colorScheme.surfaceContainerLowest
            : colorScheme.surfaceContainerLow,
        surfaceTintColor: Colors.transparent,
        indicatorColor: colorScheme.primaryContainer,
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        iconTheme: WidgetStateProperty.resolveWith((states) {
          return IconThemeData(
            color: states.contains(WidgetState.selected)
                ? colorScheme.onPrimaryContainer
                : colorScheme.onSurfaceVariant,
            size: 23,
          );
        }),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          return TextStyle(
            color: states.contains(WidgetState.selected)
                ? colorScheme.onPrimaryContainer
                : colorScheme.onSurfaceVariant,
            fontSize: 12,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w700
                : FontWeight.w600,
          );
        }),
      ),
      listTileTheme: const ListTileThemeData(
        dense: true,
        contentPadding: EdgeInsets.symmetric(horizontal: 12),
        minTileHeight: 44,
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 48),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: colorScheme.outlineVariant,
        space: 1,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: colorScheme.surfaceContainerLow,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
      ),
    );
  }
}
