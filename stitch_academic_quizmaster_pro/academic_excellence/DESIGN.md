---
name: Academic Excellence
colors:
  surface: '#faf9f8'
  surface-dim: '#dadad9'
  surface-bright: '#faf9f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f3f2'
  surface-container: '#eeeeed'
  surface-container-high: '#e9e8e7'
  surface-container-highest: '#e3e2e1'
  on-surface: '#1a1c1c'
  on-surface-variant: '#434655'
  inverse-surface: '#2f3130'
  inverse-on-surface: '#f1f0f0'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#585e6c'
  on-secondary: '#ffffff'
  secondary-container: '#dde2f3'
  on-secondary-container: '#5e6473'
  tertiary: '#943700'
  on-tertiary: '#ffffff'
  tertiary-container: '#bc4800'
  on-tertiary-container: '#ffede6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#dde2f3'
  secondary-fixed-dim: '#c1c6d7'
  on-secondary-fixed: '#161c27'
  on-secondary-fixed-variant: '#414754'
  tertiary-fixed: '#ffdbcd'
  tertiary-fixed-dim: '#ffb596'
  on-tertiary-fixed: '#360f00'
  on-tertiary-fixed-variant: '#7d2d00'
  background: '#faf9f8'
  on-background: '#1a1c1c'
  surface-variant: '#e3e2e1'
typography:
  display-lg:
    fontFamily: Source Serif 4
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Source Serif 4
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-md:
    fontFamily: Source Serif 4
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.05em
  headline-lg-mobile:
    fontFamily: Source Serif 4
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  container-max: 1140px
  gutter: 24px
  margin-mobile: 16px
  stack-lg: 40px
  stack-md: 24px
---

## Brand & Style
The design system is built upon a **Classical Premium** aesthetic, specifically tailored for high-stakes university assessments. The brand personality is authoritative, intellectual, and meticulous. It avoids the trendiness of contemporary tech startups in favor of a "Digital Ivy" feel—blending the weight of traditional academia with the efficiency of modern software.

The style is a refined mix of **Minimalism** and **Modern Corporate**. It prioritizes extreme legibility, intentional white space (breathing room for complex thought), and a strict hierarchy that guides students through rigorous examination phases without distraction. The emotional response should be one of calm focus, institutional trust, and serious purpose.

## Colors
This design system utilizes a sophisticated, light-dominant palette to reduce eye strain during long assessment periods.

*   **Primary (#2563EB):** Reserved for the most important "call to action" elements like "Submit Assessment" or "Next Section." 
*   **Secondary/Text (#1A202C):** A deep, ink-like navy used for primary headings and body text to ensure maximum contrast.
*   **Backgrounds:** The primary canvas is Warm White (#FDFCFB), while Ivory/Light-gray (#F5F5F4) is used to differentiate sidebar navigation or secondary content areas.
*   **Semantic Colors:** Success Green and Error Red are used sparingly and at a lower saturation to maintain the professional tone.

## Typography
The typography strategy employs a "Dual-Typeface" system to separate intent:
*   **Serif (Source Serif 4):** Used for titles, question prompts, and section headers. This adds the necessary academic gravitas and mimics the experience of reading a printed exam paper.
*   **Sans-Serif (Inter):** Used for all functional UI elements, body text, and input data. Its neutral, systematic nature ensures clarity in high-pressure environments.

**Key Rule:** Labels and metadata (e.g., "Time Remaining," "Question 1 of 20") should always use the Sans-Serif label style with slight letter spacing to differentiate them from the academic content.

## Layout & Spacing
The design system follows a **Fixed Grid** philosophy for the central assessment experience to maintain line lengths that are optimal for reading (60-80 characters).

*   **Desktop:** A centered 12-column grid with a maximum content width of 1140px.
*   **Gutter & Margins:** A standard 24px gutter provides ample separation between question content and navigation sidebars.
*   **Vertical Rhythm:** Use a 4px base unit. Assessments should feel airy; use "stack-lg" (40px) between major question blocks to prevent the UI from feeling cluttered or overwhelming.
*   **Mobile Adaption:** On mobile, the grid becomes a single column with 16px side margins. Serif headlines should scale down to the defined mobile-specific tokens to ensure they don't wrap awkwardly.

## Elevation & Depth
In this design system, depth is communicated through **Tonal Layers** and **Low-Contrast Outlines** rather than heavy shadows.

*   **Surface Hierarchy:** The base level is the ivory background. Content sits on top of this in white cards.
*   **Outlines:** Instead of shadows, use 1px borders in #E5E7EB to define boundaries. This creates a "paper-like" stack.
*   **Shadows:** When an element must appear elevated (like a dropdown menu or a modal), use a single, very soft, highly diffused shadow: `0px 4px 20px rgba(0, 0, 0, 0.05)`. 
*   **Focus States:** Active input fields should use a 2px solid primary blue border with no outer glow, maintaining a crisp, architectural look.

## Shapes
This design system utilizes a **Soft (0.25rem)** roundedness level. 

The goal is to move away from sharp, aggressive corners without becoming "bubbly" or informal. The slight rounding suggests a modern, approachable tool, while the predominantly straight lines maintain a sense of order and structure. Buttons and input fields should strictly adhere to the `0.25rem` radius. Exceptionally large containers (like a main assessment card) may use `0.5rem` (rounded-lg) to soften the overall viewport.

## Components
*   **Assessment Cards:** White backgrounds (#FFFFFF), 1px border (#E5E7EB), and generous padding (32px).
*   **Primary Buttons:** Solid Primary Blue (#2563EB) with white text. No gradients. Text should be Inter, Semi-Bold.
*   **Secondary Buttons:** Transparent background with a 1px border (#E5E7EB).
*   **Input Fields:** A light-gray background (#F9FAFB) with a bottom-only 2px border is preferred for a "form" feel, or a standard 4-sided 1px border for a modern SaaS feel.
*   **Progress Indicators:** Use a thin (4px) horizontal bar at the very top of the interface. This provides a constant, non-intrusive sense of progress.
*   **Question Status Chips:** Use subtle background tints (e.g., light blue for "Answered," light gray for "Unvisited") with high-contrast text. Avoid vibrant colors that might cause unnecessary anxiety.
*   **Timers:** Displayed in the top right, using the Sans-Serif font (Inter) in a tabular-nums variant to prevent the text from jumping as seconds change.