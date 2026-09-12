// The three session actions carry the glyphs users already know from
// every app: a door with an arrow for sign-out, a circular arrow for
// "run again", a cross for "decline". Inline SVG, currentColor, 14px --
// no icon dependency for three shapes. The label stays beside the glyph:
// an icon alone is a guess, a jury should not have to hover to read it.

interface Props {
  name: "signout" | "restart" | "decline";
}

const PATHS: Record<Props["name"], string> = {
  signout: "M9 3H4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h5M11 5.5 13.5 8 11 10.5M6 8h7.5",
  restart: "M13 8a5 5 0 1 1-1.5-3.6M13 3v2.4h-2.4",
  decline: "M4 4l8 8M12 4l-8 8",
};

export function Icon({ name }: Props) {
  return (
    <svg
      className="icon"
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
