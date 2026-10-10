---
source: Explanation of FAA-G-8082-22, Remote Pilot - Small Unmanned Aircraft Systems Study Guide (2016)
section: Chapter 3a (part 2 of 4)
url: https://www.faa.gov/sites/faa.gov/files/regulations_policies/handbooks_manuals/aviation/remote_pilot_study_guide.pdf#page=23
page: 23
kind: explanation
derived_from: faa-g-8082-22-chapter-3a-p2.md
---
This chunk walks through the first eight pieces of a METAR (a routine aviation weather observation report), in the order they appear in the report.

1. Type of report. There are two. The routine METAR goes out on a regular time interval. The aviation selected SPECI is a special report that can be issued at any time to update the METAR for rapidly changing weather, aircraft mishaps, or other critical information.

2. Station identifier. A four-letter code set by the International Civil Aviation Organization (ICAO). In the 48 contiguous states, a unique three-letter identifier gets the letter "K" in front of it. Gregg County Airport in Longview, Texas is "KGGG" — K for the country, GGG for the airport. Elsewhere in the world, including Alaska and Hawaii, the first two letters show the region, country, or state. Alaska always starts with "PA," Hawaii always with "PH." You can look up identifiers on sites such as DUATS and NOAA's Aviation Weather Aviation Digital Data Services (ADDS).

3. Date and time. Six digits, such as 161753Z. The first two are the date. The last four are the time, always in coordinated universal time (UTC). The trailing "Z" means Zulu time (UTC), not local time.

4. Modifier. "AUTO" means the report came from an automated source. An automated station also lists "AO1" (no precipitation discriminator) or "AO2" (with precipitation discriminator) in the Remarks section to show what precipitation sensors it has. "COR" means this is a corrected report replacing an earlier one that had an error — for example, METAR KGGG 161753Z COR.

5. Wind. Five digits, such as 14021KT, unless the speed is greater than 99 knots, in which case six digits are used. The first three digits are the direction the true wind is blowing from, in tens of degrees. Variable wind is reported as "VRB." The last two digits are the speed in knots, or three digits if the wind is greater than 99 knots. Gusts are shown by a "G" after the wind speed, followed by the peak gust recorded (G26KT). If the wind direction varies more than 60 degrees and the speed is greater than six knots, a separate group of numbers separated by a "V" gives the extremes of the wind directions.

6. Visibility. Prevailing visibility in statute miles, marked "SM," reported in both miles and fractions of miles — for example, ¾ SM. Runway visual range (RVR) may follow. RVR is the distance a pilot can see down the runway in a moving aircraft. It is written as R, the runway number, a slant, then the range in feet. R17L/1400FT means a visual range of 1,400 feet on runway 17 left.

7. Weather. Two categories: qualifiers and weather phenomenon, as in +TSRA BR. The qualifiers of intensity, proximity, and descriptor come first. Intensity is light (–), moderate (no symbol), or heavy (+). Proximity covers only phenomena in the airport vicinity; "VC" means a phenomenon is in the vicinity, five to ten miles from the airport. Descriptors describe certain types of precipitation and obscurations. The phenomena themselves may be precipitation, obscurations, or other phenomena such as squalls or funnel clouds. Weather beginning or ending, and hailstone size, are listed in the Remarks section.

8. Sky condition. Always in the sequence amount, height, and type — or indefinite ceiling/height (vertical visibility). Examples: BKN008 OVC012CB, VV003. Cloud base heights are a three-digit number in hundreds of feet above ground level (AGL). An automated station does not detect or report clouds above 12,000 feet. Towering cumulus (TCU) and cumulonimbus (CB) are reported with their height. Contractions describe the amount of cloud coverage and obscuring phenomena, and sky coverage is reported in eighths of the sky from horizon to horizon.

Gap note: Figure 3-1 (descriptors and weather phenomena) and Figure 3-2 (reportable contractions for sky condition) are referenced but their contents are not in this chunk, so the specific descriptor codes and coverage contractions are not available here.

Illustration: You plan a late-afternoon inspection flight near Longview, Texas and pull the observation: METAR KGGG 161753Z AUTO 14021G32KT 110V180 ¾SM +TSRA BR BKN008 OVC012CB. Reading it in order: KGGG is Gregg County Airport. 161753Z is the 16th of the month at 1753 UTC — you convert to local time before deciding whether this is current. AUTO tells you the report is from an automated station. 14021G32KT means the true wind is from 140 degrees at 21 knots gusting to 32 knots, and the 110V180 group tells you the direction is swinging between 110 and 180 degrees, which only appears because the variation exceeds 60 degrees with speed above six knots. ¾SM is three-quarters of a statute mile of prevailing visibility. +TSRA BR is heavy thunderstorm with rain, plus mist. The sky group reads broken at 800 feet AGL and overcast at 1,200 feet AGL with cumulonimbus. You cancel. The gust spread alone threatens control of a small unmanned aircraft, and the CB notation plus heavy thunderstorm tells you a convective cell is over the field, not nearby.

Common misreading: Two traps. First, wind direction digits are in tens of degrees, so 140 means 140 degrees — people sometimes read the three digits as a raw heading with a missing zero, or forget it is the direction the wind is blowing *from*, not toward. Second, the "Z" is not optional detail: the time is always UTC, so a 1753Z report is not a 5:53 p.m. local observation, and treating it as local can leave you planning against hours-old weather. Also note that cloud heights in the sky condition group are in hundreds of feet AGL, so OVC012 is 1,200 feet, not 12,000 — and an automated station simply will not report anything above 12,000 feet, which is not the same as the sky being clear up there.
