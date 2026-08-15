import type { CaptionStyle } from "../types";

// #29: defaultStyle di modul TERPISAH dari StyleEditor — kalau ikut
// StyleEditor, import statis di App/JobDetail membuat lazy() split tak
// berfungsi (module statis selalu masuk entry chunk).
export const DEFAULTS: CaptionStyle = {
  enabled: true,
  font: "Montserrat Black",
  size: 96,
  bold: true,
  italic: false,
  uppercase: false,
  pop: false,
  bounce: false,
  auto_emoji: true,
  spacing: 0,
  line_spacing: 0,
  text_color: "#FFFFFF",
  highlight_color: "#FFFF00",
  outline: 6,
  outline_color: "#000000",
  border_style: "outline",
  shadow: 3,
  shadow_color: "#000000",
  position: "bottom",
  margin_v: 240,
  style: "highlight",
};

export function defaultStyle(): CaptionStyle {
  return { ...DEFAULTS };
}