# Changelog

All notable changes to WootFlow are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added
- Perfis de jogo (página Jogos): cada perfil liga um ou mais executáveis a um efeito, com brilho, velocidade e cores opcionais. O WootFlow troca de efeito quando o jogo abre (ou fica em primeiro plano) e repõe o teu efeito quando fecha
- Efeito «HUD do jogo»: lê barras do HUD no ecrã (vida, escudo...) e mostra-as numa fila do teclado, com pulsação em vida baixa e flash ao levar dano. Calibração na página Jogos (captura, região e cor da barra)
- Modo de Suspensão RGB e filtro Debounce nas Definições (o debounce só fica guardado)

### Fixed
- Leitura do tipo e layout do teclado pelo SDK (os enums têm 4 bytes)
- Geometria do Screen Ambience alinhada com as 66 células do 60HE+

---

## [3.3.0] - 2026-11-03

### Added
- Deteção do modelo Wooting ligado e adaptação dos efeitos ao seu formato (60HE com layout medido; outros formatos com grelha aproximada)
- Pré-visualização do teclado ao estilo Wootility, também na barra de topo dos separadores Efeitos e Som
- Vista "Ao vivo" na página Teclado com a profundidade de cada tecla (Wooting Analog SDK)
- Modelo e formato do teclado mostrados na UI e em Definições

### Changed
- Interface com o aspeto do Wootility: paleta, fonte Nunito Sans e nova barra lateral com ícones
- Screen Ambience passa a capturar o monitor 27G4ZR em vez do VG248

---

## [3.2.3] - 2026-05-08

### Added
- Auto arranque no Windows com toggle em Definicoes

### Changed
- Quando iniciado por auto arranque, o app abre minimizado para a tray (`--start-hidden`)

### Fixed
- Estado de auto arranque sincronizado entre registo do Windows e painel de Definicoes

---

## [3.2.1] – 2026-05-05

### Fixed
- Screen ambience zone mapping now auto-fills uncovered LEDs from the 60HE physical layout
- Tray icon stability improvements on Windows 11

### Changed
- Build artifacts reorganized: portable ZIP and installer EXE follow consistent `WootFlow-vX.Y.Z-win-*` naming

---

## [3.2.0] – 2026-04-01

### Added
- Audio reactive effect (pulses keyboard to system audio / music)
- Screen ambience per-key canvas sampling (SignalRGB-style)
- Profile system: save and switch multiple lighting profiles

### Changed
- Migrated frontend to React + Vite + Tailwind CSS
- Replaced legacy HTTP polling with WebSocket communication

---

## [3.1.0] – 2026-02-15

### Added
- System tray integration (run in background, right-click menu)
- Per-key customization panel in UI

### Fixed
- Wave effect hue drift at high frame rates

---

## [3.0.0] – 2026-01-10

### Added
- Initial public release
- Dynamic effects: wave, ripple, reactive typing, fire, aurora, matrix rain, starfield, equalizer, gradient
- FastAPI backend with WebSocket live control
- pywebview desktop shell
- Windows installer via Inno Setup
- GitHub Actions CI/CD pipeline

[Unreleased]: https://github.com/carloscosta2025086-web/WootFlow/compare/v3.2.3...HEAD
[3.2.3]: https://github.com/carloscosta2025086-web/WootFlow/compare/v3.2.2...v3.2.3
[3.2.1]: https://github.com/carloscosta2025086-web/WootFlow/compare/v3.2.0...v3.2.1
[3.2.0]: https://github.com/carloscosta2025086-web/WootFlow/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/carloscosta2025086-web/WootFlow/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/carloscosta2025086-web/WootFlow/releases/tag/v3.0.0
