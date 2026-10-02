# KherveSlide User Guide

KherveSlide is a slide designer that works like PowerPoint — you drag,
resize and stack text, pictures and shapes freely on a slide — but your
presentation is written as LaTeX **beamer** and compiled to a PDF. You get
the ease of PowerPoint and the typesetting of LaTeX: real equations,
consistent themes, and a PDF that looks the same on every computer.

Press **F1** at any time to open this guide.

## Getting started

When KherveSlide starts, the **Welcome page** fills the slide area:

- **New presentation**, **Open…**, **Import PowerPoint…** and
  **Continue** (back to what was open).
- **Templates** — empty presentations with a starting layout.
- **Example presentations** — complete talks that show what KherveSlide
  can do. Open one, look at how it is built, and change anything.
- **How do you want to work?** — see *Ways of working* below.
- **Recent** — your recent presentations, listed on the left.

Untick *Show this page when KherveSlide starts* to skip it.
**Help → Welcome page** brings it back at any time.

You can also open a presentation by **dragging a `.kslide` file onto the
window** (a `.pptx` dropped the same way is imported).

## Ways of working

| Mode | What you see | Shortcut |
|------|--------------|----------|
| **Visual + PDF side by side** | The slide on the left, the compiled PDF on the right, updated as you edit. | `Ctrl+4` |
| **Visual + PDF in its own window** | The PDF and console in a separate window (put it on a second screen). Close it to dock it back. | `Ctrl+5` |
| **Visual only** | Just the slides and the editor, like PowerPoint. Nothing compiles while you work. | `Ctrl+6` |

Switch from the **View** menu or the PDF button at the right of the
toolbar.

## The window

- **Slides** (left) — a thumbnail of every slide. Click one to edit it,
  drag it to reorder. Fold the list away with **«** (or `Ctrl+B`) and
  bring it back by clicking the thin *Slides* strip.
- **Visual** tab — the slide you are editing. It is drawn to look like
  the PDF: same fonts, the theme's title bar, footer and bullets.
- **LaTeX** tab — the beamer source of the whole presentation, kept up
  to date as you edit. You can edit it by hand; *Regenerate from slides*
  returns to the slides as the source.
- **Console** tab — the LaTeX log of the last compile; look here when
  the PDF does not appear.
- **PDF** and **Overview** (right, in the side-by-side mode) — the
  compiled result and every slide as a mini page.
- **Frame / Header / Foot** fields — around the slide; see
  *Titles, headers and footers*.
- **The bar at the bottom**, as in PowerPoint: *Slide 3 of 12*, the
  **Theme** button (the same menu as View → Slide theme), the three
  views, the **slideshow** button (from the current slide; its arrow
  offers the other ways) and the zoom (out, fit, in).

### Normal, Overview and Master

- **Normal** — one slide in the Visual editor.
- **Overview** — every slide as a mini page, in the *Overview* tab of
  the right frame (or in the slide's place when you work in Visual
  only). Click a slide to go to it, double-click to edit it, drag to
  reorder, right-click for the slide menu; the *Size* slider makes the
  mini pages bigger or smaller.
- **Master** — the template behind every slide. What you put on it — a
  logo, a line, a text, a picture — shows on all the slides, behind
  their own content. The slides list then holds the master alone; an
  orange bar says you are in the master, with **Close master view** to
  go back. All three are also in the **View** menu.

## Slides

- **Add a slide**: the **+** button on the left toolbar (its small arrow
  offers layouts with a picture of each), or **Slide → Add slide with
  layout**.
- **Right-click a slide** in the list to apply a layout to it, add a new
  slide after it, duplicate, move, hide / show or delete it. **Delete**
  removes the selected slide too.
- **Move a slide**: drag it up or down in the list — an orange line shows
  where it will land — or `Ctrl+Shift+↑` / `↓`.
- **Hide a slide** (right-click ▸ *Hide slide*, or **Slide → Hide / show
  slide**): it stays in the presentation, faded in the list with its
  number struck through, but is left out of the PDF and the slideshow.
  *Show slide* brings it back.
- **Background colour**: **Slide → Background colour…**.

## Text

- **Add a text box**: the **T** button on the left toolbar, **Insert →
  Text box**, or right-click an empty part of the slide.
- **Type into a box**: double-click it. Click outside it (or press
  `Esc`) when you are done.
- **Format**: the toolbar at the top follows the selected box — font,
  size, **bold** / *italic* (`Ctrl+B` / `Ctrl+I` while typing),
  superscript, subscript, alignment, text and fill colours, bullets and
  numbered lists.
- **Bullets** look like the theme's own bullets (balls, triangles…).
  Press `Tab` / `Shift+Tab` on a bullet to make it a sub-bullet or back.
- **Maths in text**: type it between dollar signs, e.g. `$E = mc^2$`.
- **Box type** (the *Box* list on the toolbar): plain text, a beamer
  block (*block*, *alert block*, *example block*), or a theorem,
  definition, proof… with their own title bar.

### Locked and free boxes

Every object is either **free** — you place it exactly where you want
and it lands there in the PDF — or **locked**, in which case beamer lays
it out in the normal flow of the slide. Right-click an object and use
**Lock position** (or click its padlock badge) to switch. Every box is
free to start with — text, titles, pictures, tables, and the boxes of
every layout and template — so you can drag it straight away; lock it
only when you want beamer to place it. (Presentations saved earlier keep
the lock each box had.)

Hover over any toolbar icon for a detailed tooltip: what it does, how to
use it step by step, and a tip.

## Pictures, video and drawings

- **Picture**: **Insert → Picture**, the picture button, or simply drag an
  image file onto the slide. Double-click a picture to crop, rotate,
  replace or draw on it. Right-click for transparency, aspect lock and
  *Export to PNG*.
- **Video**: **Insert → Video…** — shown with a poster image; in the PDF
  it is a click-to-play link.
- **Drawing**: **Insert → Drawing…** opens the drawing editor (shapes,
  arrows, dimensions, flowchart, electrical, optics, maths and labware
  symbols). The drawing is placed as a sharp vector picture;
  double-click it to edit it again.

## Equations and chemistry

- **Equation builder** (`Ctrl+Shift+E`): build the equation visually —
  fractions, integrals, matrices, Greek letters — or type LaTeX. The box
  shows the rendered equation; double-click it to edit.
- **Chemical reaction** (`Ctrl+Shift+R`): reactions written the mhchem
  way, e.g. `2H2 + O2 -> 2H2O`, with a live preview.
- **Chemical structure** (`Ctrl+Shift+T`): molecules drawn with chemfig
  (rings, bonds, wedges), placed as a sharp picture; double-click it to
  edit.

## Flowcharts

**Flowchart builder** (`Ctrl+Shift+F`, or the flowchart button on the
left toolbar) builds a LaTeX (TikZ) flowchart by clicking:

- **Click a shape** in the palette — start / end, process, decision,
  input / output, document, data, sub-process, connector, note — to add
  it after the selected box, joined by an arrow. A chain grows as fast
  as you click.
- **Drag** boxes to move them (they snap to a grid); **Ctrl / ⌘-click**
  another box to draw an arrow to it; **Delete** removes the selection.
- **Edit** the text of a box, or the label of an arrow (*Yes*, *No*…), in
  the panel on the right; LaTeX maths is welcome, and `\\` starts a new
  line. Arrows can be automatic, straight or elbowed, and dashed.
- **Arrow** and **Line** tools (end of the palette): click the box it
  starts from, then the box it goes to; keep clicking pairs to draw
  more, and click empty space to stop. A line has no arrowhead.
- **Which way it points**: select a link and choose its **Arrowheads**
  — arrow, reversed arrow, both ends, or a plain line (also on its
  right-click menu); **Reverse direction** swaps its ends.
- **Which sides it joins**: **Leaves from** and **Arrives at** pick the
  top, bottom, left or right of each box (or Automatic) — handy for
  loops and links that go round other boxes.
- **Curves**: the **Curve** tool, or *Route → Curved*. **Bend** sets how
  much it bows (positive to the left, negative to the right); when both
  sides are chosen the curve leaves the one and arrives into the other.
- **Direction**: top to bottom, or left to right. **Colours**: your
  presentation's own, or a ready-made scheme. **Tidy up** lays the chart
  out by itself. **Start from** offers ready-made charts.
- The **preview** is compiled with LaTeX — exactly what lands on the
  slide. **Show LaTeX** gives the TikZ code.

The chart is placed on the slide as a sharp picture; double-click it to
edit it again. Its TikZ code is saved beside the presentation
(`figures/flowchart_001.tikz`) to reuse in any LaTeX document.

## Tables, shapes and lines

- **Insert → Table** — pick the size; double-click a cell to type in it.
  **Table design…** offers ready-made styles; right-click for rows,
  columns, header row, caption and properties.
- **Insert → Shapes** — rectangles, ellipses, arrows, stars, speech
  bubbles… Right-click a shape for its colours, outline and transparency.
  Put a text box on top of a shape to label it.
- **Lines and arrows** — from the left toolbar; drag their ends.

## Arranging objects

- **Select several**: drag a rectangle around them, or `Ctrl`-click
  (`⌘`-click on a Mac).
- **Group** (`Ctrl+G`) / **Ungroup** (`Ctrl+Shift+G`).
- **Order**: bring to front / send to back from the left toolbar or the
  right-click menu.
- **Grid and snapping**: **View → Show grid** (`Ctrl+'`), **Grid size**,
  **Snap to grid**, **Snap to objects**.
- **Copy / paste / duplicate**: `Ctrl+C` / `Ctrl+V` / `Ctrl+D` — also
  between two KherveSlide windows (**File → New window**).

## Titles, headers and footers

- **Frame title**: the *Frame* field above the slide — it appears in the
  theme's title bar.
- **Header** and **Left / Centre / Right foot**: the fields around the
  slide. **Double-click a field** to pick what goes in it: slide number,
  *n / N*, today's date, the year, the presentation title, the author…
  each shown with how it will look.
- **Slide numbers** and **navigation symbols**: **Edit → Presentation**.
- **Title and author** of the presentation: **Edit → Presentation**.

## Themes

Everything about the look is in **View → Slide theme** — also the
**Theme** button in the bar at the bottom of the window:

- **Presentation theme** — the classic beamer themes (Madrid, Berlin,
  Warsaw…). **Preview themes…** shows them side by side.
- **Colour theme** — recolour the current theme.
- **Theme wizard** — the easy way to your own theme, in five steps:
  1. **Start** from a style (including university-style colours) or
     **import your template**: a PowerPoint template (`.potx` / `.pptx`),
     a beamer theme (`.sty` or an Overleaf `.zip`), or a picture / PDF
     of one of your slides.
  2. **Colours** — main colour, accent, text and background.
  3. **Logo** — your logo, its corner and size (drawn on every slide).
  4. **Title & footer** — a coloured title bar, a coloured title, or a
     title with a line; a footer bar (author · title · slide number), a
     thin line, or nothing.
  5. **Typeface & bullets**, then a name. Themes are kept in *My themes*
     for your other presentations.

  A live preview, compiled with LaTeX, shows the result as you go.
- **Advanced theme builder** — every beamer setting, for fine control,
  and **export as a standard beamer `.sty`** to use in any LaTeX project.
- **Show theme decorations** — switch the title bars and footers off for
  plain slides.

**Edit → Page setup…** sets the slide shape (16:9, 4:3…), a custom size
and the margin.

## Templates and examples

- **File → Templates → New presentation from template**.
- **File → Templates → Save current presentation as template…** turns
  your presentation into a template (rename or delete them there too).
- **File → Example presentations** — a research talk, a lecture, a
  project update, a maths seminar, diagrams & workflows, and a dark
  lightning talk.

## Compiling and the PDF

- The PDF compiles automatically shortly after each change (in the two
  PDF modes). The round green-arrow button turns this on or off; the
  green **▶** button (`Ctrl+R`) compiles now.
- **Skip images** (toolbar) compiles faster with placeholder boxes
  instead of pictures — handy for long presentations.
- **File → Export PDF…** saves the PDF; **File → Export LaTeX (.tex)…**
  saves the beamer source.
- Compiling works **offline**: the LaTeX packages are kept on your
  computer. **File → Download LaTeX packages (offline)…** fetches all of
  them in one go, e.g. before travelling.

## Slideshow

Present the compiled PDF full screen from the **Slideshow** menu:

| Command | What happens | Shortcut |
|---------|--------------|----------|
| **From the beginning** | Full screen from slide 1. | `F5` |
| **From the current slide** | Full screen from the slide you are on. | `Shift+F5` |
| **Presenter view** | The slides on the other screen; on yours, the current and next slide, the slide count, a timer and the clock. | `Alt+F5` |
| **Current + next slide** | Two screens: the current slide on one, the next on the other. | |
| **In a window** | A normal, resizable window — beside other work or shared in a video call — with a player bar (see below). `F` switches it to full screen and back. | |

**Show the slides on** chooses the screen (normally the other one).

### The slideshow window

A slideshow **in a window** has a player bar under the slides: first,
previous, **Play / Pause** and next; **Each slide** (seconds);
**Once**, **Loop** or **Loop for…** (minutes); a *next in … s*
countdown; the slide number; full screen and end. Press **Play** (or
`S`) at any time to let the slides advance by themselves, and again to
pause; change the seconds or the repeat while it runs. A *Once* run
stops on the last slide and leaves the window open, ready to play
again. In full screen the bar hides, and comes back when you move the
mouse.

### Automatic slideshow

**Slideshow → Automatic slideshow…** plays the slides by themselves —
for a kiosk, a poster session or a looping display. Choose:

- **Each slide shows for** — the number of seconds per slide.
- **Repeat** — *once through, then end*; *loop continuously* (until
  `Esc`); or *loop for a set time* (in minutes).
- **Show as** — full screen, in a window, or presenter view, and
  whether to start from the current slide.

During an automatic show, `S` pauses and resumes it; the arrow keys
still move by hand (each slide then gets its full time again); a blank
screen (`B` / `W`) holds the countdown. The presenter view shows how
long until the next slide. Your choices are remembered.

During the show: `→`, `Space`, `Page Down` or a click go forward; `←`,
`Page Up` or a right-click go back; `Home` / `End`; type a number and
press `Enter` to jump; `B` / `W` blank the screen black / white; `Esc`
ends the show.

## Saving and version history

- **File → Save** (`Ctrl+S`) saves a `.kslide` file (a `.tex` copy is
  written next to it). Every action can be undone with `Ctrl+Z` and
  redone with `Ctrl+Y`.
- **Git** menu — every save also records a version, so you can go back:
  **View version history…**, **Branches…**, and **Connect to GitHub /
  GitLab…** to keep a copy online (**Save snapshot and upload** /
  **Download latest from cloud**).

## Spelling and finding text

- Misspelt words are underlined in red; right-click one for suggestions.
  **View → Check spelling** turns it on or off, **Spell-check language**
  picks the language, **Edit → Check spelling…** (`F7`) goes through the
  whole presentation.
- **Edit → Find…** (`Ctrl+F`) finds text across all slides.

## AI assistant (Claude)

**AI → Connect to Claude…** lets an AI assistant such as Claude Desktop
or Claude Code work on the presentation you have open — add slides,
write and lay out content, build a theme from your university's
template, check each slide as an image. Tick *Let assistants connect*,
press **Connect** next to your application, and restart it. Choose how
much the assistant may do (*Read only*, *Edit* or *Full*). Everything it
changes can be undone with `Ctrl+Z`.

## Updates

**Help → Check for updates…** looks for a newer KherveSlide on GitHub;
**Update automatically** does it in the background and offers to
restart when an update has been installed.

## Keyboard shortcuts

| Action | Shortcut |
|--------|----------|
| New / Open / Save / Save As | `Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` |
| New window | `Ctrl+Shift+N` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Y` |
| Copy / Cut / Paste / Duplicate | `Ctrl+C` / `Ctrl+X` / `Ctrl+V` / `Ctrl+D` |
| Group / Ungroup | `Ctrl+G` / `Ctrl+Shift+G` |
| Find / Check spelling | `Ctrl+F` / `F7` |
| Compile now | `Ctrl+R` |
| Equation builder / Chemical reaction / Chemical structure | `Ctrl+Shift+E` / `Ctrl+Shift+R` / `Ctrl+Shift+T` |
| Flowchart builder | `Ctrl+Shift+F` |
| Move slide up / down | `Ctrl+Shift+↑` / `Ctrl+Shift+↓` |
| Show / hide the slides list | `Ctrl+B` |
| Show grid | `Ctrl+'` |
| Side by side / PDF window / Visual only | `Ctrl+4` / `Ctrl+5` / `Ctrl+6` |
| Slideshow / from current slide / presenter view | `F5` / `Shift+F5` / `Alt+F5` |
| This guide | `F1` |

## Troubleshooting

- **The PDF does not appear** — look at the **Console** tab for the
  LaTeX message. A missing package is downloaded automatically the
  first time you are online.
- **A theme or font is missing offline** — run **File → Download LaTeX
  packages (offline)…** once while connected.
- **Text looks different on the slide and in the PDF** — check the PDF:
  it is the reference. Locked boxes are placed by beamer, so they may sit
  elsewhere in the PDF; unlock them to place them exactly.
