// The source line a secondary view ends with (ux-guidelines § 2.5, § 4): the same short
// "Date: <sursă>, <an>" the first screen prints, so no view ships a figure without it.
export default function ViewSource({ text }: { text: string }) {
  return <p className="view-source">{text}</p>;
}
