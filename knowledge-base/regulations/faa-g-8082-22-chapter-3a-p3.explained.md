---
source: Explanation of FAA-G-8082-22, Remote Pilot - Small Unmanned Aircraft Systems Study Guide (2016)
section: Chapter 3a (part 3 of 4)
url: https://www.faa.gov/sites/faa.gov/files/regulations_policies/handbooks_manuals/aviation/remote_pilot_study_guide.pdf#page=23
page: 23
kind: explanation
derived_from: faa-g-8082-22-chapter-3a-p3.md
---
This chunk finishes the list of METAR (routine aviation weather report) elements and then starts on forecasts.

The last four METAR elements:
- Temperature and dew point are always in degrees Celsius (C), written as two numbers separated by a slash, such as 18/17. A temperature below 0 °C gets the letter "M" in front of it for minus.
- Altimeter setting is reported in inches of mercury ("Hg) as a four-digit group preceded by "A," such as A2970. If pressure is rising or falling, the Remarks section may say "PRESRR" or "PRESFR."
- Zulu time is aviation's term for UTC (Coordinated Universal Time), which puts the whole world on one time standard.
- Remarks always begin with "RMK." This section may or may not be present. It can hold wind data, variable visibility, start and end times of a weather phenomenon, pressure information, and anything else judged necessary. OCNL LTGICCG means occasional lightning in the clouds and from cloud to ground. Automated stations also use Remarks to flag that their equipment needs maintenance.

The chunk's worked example: METAR KGGG 161753Z AUTO 14021G26KT 3/4SM +TSRA BR BKN008 OVC012CB 18/17 A2970 RMK PRESFR. That is a routine METAR for Gregg County Airport, 16th day of the month at 1753Z, from an automated source. Wind 140 at 21 knots gusting to 26. Visibility 3/4 statute mile. Thunderstorms with heavy rain and mist. Ceiling broken at 800 feet, overcast at 1,200 feet with cumulonimbus clouds. Temperature 18 °C, dew point 17 °C. Pressure 29.70 "Hg and falling rapidly.

Then the chunk turns to forecasts. Observed weather reports are often used to build forecasts for the same area, and forecasts are meant for the preflight planning stage. The printed forecasts pilots should know are the terminal aerodrome forecast (TAF), the aviation area forecast (FA), inflight weather advisories — Significant Meteorological Information (SIGMET) and Airman's Meteorological Information (AIRMET) — and the winds and temperatures aloft forecast (FB).

A TAF covers a five statute mile radius around an airport and is usually issued for larger airports. Each TAF is valid for a 24 or 30-hour period and is updated four times a day at 0000Z, 0600Z, 1200Z, and 1800Z. It uses the same descriptors and abbreviations as a METAR. Its elements, in order, begin with: type of report (TAF for routine, TAF AMD for amended); ICAO station identifier, same as in a METAR; date and time of origin as a six-number code like 081125Z, where the first two digits are the date and the last four are the time, always in UTC as shown by the Z; and the valid period dates and times, like 0812/0912, which follows the origin group. In 0812/0912, 08 is the day of the month the TAF starts, 12 is the starting hour in UTC, 09 is the day of the month it ends, and the last 12 is the ending hour UTC. A forecast period beginning at midnight UTC is written as 00. The chunk cuts off mid-sentence on what happens if the end time of a valid period is something particular — see the rest of that section.

Illustration: You plan a late-afternoon roof inspection and pull the METAR in the chunk's example for your nearby airport: 18/17 A2970 RMK PRESFR, with +TSRA BR and BKN008 OVC012CB. You read it element by element. Temperature 18 °C and dew point 17 °C are only one degree apart, which is why mist (BR) is being reported and visibility is down to 3/4 statute mile. The Remarks say PRESFR — pressure falling rapidly — and the body of the report shows thunderstorms with heavy rain and cumulonimbus at 1,200 feet. You also pull the TAF for that airport, noting it covers the five statute mile radius around the field and that the valid period group tells you which hours the forecast actually covers. You scrub the flight and reschedule, because the report and forecast together describe an active thunderstorm with deteriorating pressure, not a passing shower.

Common misreading: Two traps here. First, the "M" prefix on temperature means minus, not "missing" — M05 is 5 degrees below zero Celsius. Second, a TAF is not a report of current conditions and is not for your exact launch site. It is a forecast built for the five statute mile radius around an airport, usually a larger one, so if you are operating well outside that circle the TAF describes the airport's expected weather, not necessarily yours.
