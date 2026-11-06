# Workstation fonts

Original variable font binaries, downloaded 2026-11-06 from Google Fonts' official repository:

- `InterTight-variable.ttf`: https://github.com/google/fonts/blob/main/ofl/intertight/InterTight%5Bwght%5D.ttf
- `JetBrainsMono-variable.ttf`: https://github.com/google/fonts/blob/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf

Unmodified, normal style, with the accompanying family-specific SIL Open Font License files. Full glyph coverage is preserved, including Greek financial notation. The application exposes weights 400–700 and the same CSS variables as before.

`next/font/local` removes the build-time Google CSS dependency. The previous Google loader failed while deriving a file extension from a returned font URL in Vercel preview. This is a packaging repair, not a change of design language. Reference: https://nextjs.org/docs/app/api-reference/components/font#local-fonts
