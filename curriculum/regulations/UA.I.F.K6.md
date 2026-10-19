---
source: 14 CFR 89.305 | https://www.ecfr.gov/current/title-14/section-89.305
source: 14 CFR 89.315 | https://www.ecfr.gov/current/title-14/section-89.315
source: 14 CFR 89.310 | https://www.ecfr.gov/current/title-14/section-89.310
source: 14 CFR 89.320 | https://www.ecfr.gov/current/title-14/section-89.320
source: AC 107-2A | https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC_107-2A.pdf
version: 1
---
Objective: know which message elements each kind of remote identification broadcasts, and how the two sets differ.

A standard remote identification unmanned aircraft must be able to broadcast the elements in 89.305: the identity of the aircraft, which is either a serial number assigned by its producer or a session ID; the latitude and longitude of the control station; the geometric altitude of the control station; the latitude and longitude of the aircraft; the geometric altitude of the aircraft; the velocity of the aircraft; a time mark giving the Coordinated Universal Time of the position; and the emergency status of the aircraft. Under 89.310 the control station location must correspond to the location of the person manipulating the flight controls.

A remote identification broadcast module must be able to broadcast the elements in 89.315: the identity of the aircraft, as the serial number assigned to the module; the latitude and longitude of the aircraft; its geometric altitude; its velocity; the latitude and longitude of the takeoff location; the geometric altitude of the takeoff location; and a time mark. The two sets differ in three ways. The module broadcasts the takeoff location where the standard aircraft broadcasts the control station location. The module has no emergency status element. And the module's identity is always its own serial number, with no session ID.

Both must broadcast at a rate of at least 1 message per second, with the position and altitude broadcast no later than 1.0 seconds after measurement, using a non-proprietary specification on radio spectrum that personal wireless devices can receive. The reported position of the aircraft must be accurate to within 100 feet with 95 percent probability, and its altitude to within 150 feet.

Worked example: a police officer with a receiver picks up a broadcast from an aircraft over a stadium. From a standard aircraft the officer reads the control station's position and walks to the pilot. From a module the officer reads the takeoff location instead, which is where the aircraft left the ground, not necessarily where the pilot now stands.

Common misreading: assuming both kinds broadcast the pilot's location. Only the standard aircraft broadcasts the control station; the module broadcasts the takeoff point.
