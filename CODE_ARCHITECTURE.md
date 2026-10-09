# Code architecture

Choices about how the code is shaped that are meant to stay that way, so a
review does not flag them as defects.

## The front end words the board's facts itself

The board API serves facts and codes, not sentences. The web front end
(`frontend/app/data/dashboard.ts`) turns those facts into its own wording, and
sentences do not move back onto the server: another front end would word the
same facts its own way.
