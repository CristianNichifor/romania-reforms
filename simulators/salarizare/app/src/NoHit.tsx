/**
 * The empty state of the home search (design screen 03, criterion 7): it names what was
 * searched and says what to try next, instead of a generic "nothing found".
 */
export default function NoHit({ query }: { query: string }) {
  return (
    <p className="home-nohit empty-state" role="status">
      Niciun post pentru „{query.trim()}” în grila proiectului. Denumirile sunt cele din anexe,
      iar multe posturi reale sunt comasate sub un titlu care nu le conține: încearcă cuvântul cel
      mai general din meserie (de exemplu „asistent” în loc de „asistent medical principal”) sau
      alege o secțiune din meniu.
    </p>
  );
}
