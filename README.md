# Cards Battlers Playgrounds

**Status: In-progress / Paused**  
*This project is not strictly discontinued - it still carries a lot of value. It stopped at a nearly-done state that feels like the wrong direction, and it will either be simplified and reborn or revived here. The git commits are the journal.*

## Overview

Cards Battlers Playgrounds (CBP) is a card-battle playground built as a MUGEN-style, data-driven engine: the game itself is just a rule engine, and everything you see - characters, cards, decks, places, teams - is plain JSON data living in `data/`. On top of that sits a simulated world where AI characters live their own lives: they walk around, idle, duel each other, fight team battles, trade cards, request borrows, bet and run championships, all simulated locally in plain JSON state.

It is a single-file pygame application (`cbp.py`, roughly 15K lines) driven by a design document (`gdd.txt`) that defines the whole MUGEN-style card engine concept: load only the data a scene needs, keep all state human-readable, and let the world run with or without the player watching it.

One thing to be clear about: the "smart AI" is not real AI models. There are no ML libraries anywhere. Every character is driven by LogicGraph behaviors and weighted decision tables - hardcoded scripts, in other words. They produce surprisingly alive behavior for scripts, but that is what they are.

## What Is Working

- **Living world simulation** - Characters advance through idle life, movement, duels, team battles, trades, borrow requests, championships, betting and a traders pool, tick by tick, with every actor making its own decisions
- **Full duel engine** - Complete card duels with zones, piles, attack/defense, phases and a full duel scene UI
- **Data-driven everything** - Cards, characters, decks, teams, places, media and world state are all JSON; shared art lives in `data/universal_assets`
- **Windows builds** - A GitHub Actions workflow (manual dispatch) builds the game with PyInstaller, smoke-tests it, zips it with maximum deflate and uploads it as an artifact. No releases - artifacts only
- **Stable memory** - The infamous +13GB boot bug is fixed (see below)

## What Went Wrong And Got Fixed

The first public test consumed over 13GB of RAM within seconds of reaching the main menu. The cause was a time bomb, literally: the committed world state (`data/runtime/world/index.json`) carried a stale wall-clock timestamp from the Unix epoch, so the first simulation tick computed a catch-up of roughly 1.8 billion simulated seconds. The idle-life loop then dutifully tried to materialize ~60 million pending event objects in one go, which is where the gigabytes came from.

The fix clamps world catch-up ticks to a sane budget (`catchup_seconds`, 30 by default), bounds the idle cue loop, and puts byte budgets on the internal image/text caches. Boot now sits at a flat ~200MB and stays there.

## Known Issues And Limitations

- **Low FPS for no obvious reason** - The game runs far below what it should on modest hardware, while engines like MUGEN or Ikemen GO render busy fights smoothly. Nothing in the workload justifies it; the render and simulation layers need real profiling and optimization. This is the biggest technical debt in the project
- **Monolithic single file** - The entire engine, world simulation, every scene and every widget live in one ~15K-line file with no comments. It works, but it is hostile to navigate
- **Scripted AI only** - LogicGraphs and weights, not models. Fine for now, but it caps how smart the world can feel
- **Scope drift** - The meta-world (trades, borrows, championships, betting) grew bigger than the dueling itself, and dueling is the part that actually plays best
- **No versions, no releases, no documentation** - Development was tracked purely through git commits

## The Likely Future

Two honest paths, undecided:

1. **Simplify and port to Godot** - Strip away the meta-world and animations, keep pure card battling, and rebuild in Godot as a cards-focused dueling game: something like MUGEN or Ikemen but for cards. An open card maker with deep customization and exact, correct rule logic, where adding cards is as easy as dropping in data (the way YGO modding already adds cards and scripts them normally). This is the direction the project is most likely to take
2. **Optimize in place** - Keep the pygame codebase, profile the render loop until the FPS is respectable, and split the monolith into modules. More work, same architecture

Either way, this repository stays as the reference implementation and the journal of how far it got.

## For Developers

### Run From Source

```bash
git clone https://github.com/HAKORADev/Cards_Battlers_Playgrounds.git
cd Cards_Battlers_Playgrounds
pip install pygame-ce
python cbp.py
```

- Python 3.10+ recommended, pygame-ce required
- The `data/` folder must sit next to `cbp.py` - it carries the whole world
- `gdd.txt` is the design law; the code follows it

### Building For Windows

The CI way: run the `windows-build` workflow from the Actions tab (manual dispatch). It produces a `CBP-windows` artifact containing the zipped build - exe, data and icons.

The local way:

```bash
pip install pygame-ce pyinstaller
pyinstaller cbp.spec
```

The spec embeds `logo.ico` as the executable icon and packages `logo.png` + `logo.ico` beside the exe so the window and taskbar pick them up too.

### A Note On The Logo

`logo.png` and `logo.ico` are placeholders: they are the game's own "?" normal-monster placeholder card, composed from `data/universal_assets`. The real logo exists on another disk and will replace these later.

## License

MIT License - See LICENSE file for details.

---

**Final Note:** This project died in a state that was nearly done but felt like the wrong direction - which is a strange place to stop, and probably not a stopping place at all. The engine runs, the world simulates, the duels play. If it does not transform into its next form, the code and the data format remain here as a working reference for anyone building a data-driven card game engine.
