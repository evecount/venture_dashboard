/**
 * The dashboard's theme follows the time of day:
 *   8am–6pm             day
 *   6pm → sunset        drifts, minute by minute, into a warm "night shift" off-white (unnoticeable as it happens)
 *   sunset → dusk       stays warm
 *   dusk → dawn         night (dusk/dawn = civil twilight: the sun is 6° below the horizon, fully set)
 *   dawn → sunrise      warm again
 *   sunrise → 8am       drifts back to plain day
 * The knob's red mark is an hour hand (1am or 1pm → 1 o'clock); its colours follow the phases above.
 * A click on the knob holds day or night until the clock itself next switches night on/off, then the clock carries
 * on. Clicking back to what the clock says returns to automatic straight away.
 *
 * This is a plain-JS string because it must run in <head> before the first paint (no flash), and the React
 * toggle uses the very same code through window.__vdTheme. Keep it ES5-ish and self-contained.
 */
export const THEME_CORE = `(function(){
var DAY=864e5, HOUR=36e5, MIN=6e4, RAD=Math.PI/180;
var KEY="vd_theme", POS="vd_theme_pos";
var HOME={lat:1.3521, lon:103.8198}; // Singapore, where the studio is; the device's location is used once allowed

// Sun times for the day containing t (SunCalc-style algorithm). Returns ms timestamps.
function sun(t, lat, lon){
  var J1970=2440588, J2000=2451545, lw=-lon*RAD, phi=lat*RAD;
  var d=t/DAY-0.5+J1970-J2000;
  var n=Math.round(d-0.0009-lw/(2*Math.PI));
  var ds=0.0009+lw/(2*Math.PI)+n;
  var M=RAD*(357.5291+0.98560028*ds);
  var C=RAD*(1.9148*Math.sin(M)+0.02*Math.sin(2*M)+0.0003*Math.sin(3*M));
  var L=M+C+RAD*102.9372+Math.PI;
  var dec=Math.asin(Math.sin(RAD*23.4397)*Math.sin(L));
  var noon=J2000+ds+0.0053*Math.sin(M)-0.0069*Math.sin(2*L);
  function at(h){
    var c=(Math.sin(h*RAD)-Math.sin(phi)*Math.sin(dec))/(Math.cos(phi)*Math.cos(dec));
    var w=Math.acos(Math.max(-1,Math.min(1,c)));
    var j=J2000+0.0009+(w+lw)/(2*Math.PI)+n+0.0053*Math.sin(M)-0.0069*Math.sin(2*L);
    return [(noon-(j-noon)+0.5-J1970)*DAY, (j+0.5-J1970)*DAY]; // [rise, set]
  }
  var s=at(-0.833), c=at(-6);
  return {sunrise:s[0], sunset:s[1], dawn:c[0], dusk:c[1]};
}

function clamp(x){ return x<0?0:x>1?1:x; }

// Where the clock says we are. offsetMin = the viewer's minutes east of UTC.
// Returns {dark, warm (0..1), next (ms of the next change)}.
function phase(now, lat, lon, offsetMin){
  var off=offsetMin*MIN, mid=Math.floor((now+off)/DAY)*DAY-off; // local midnight
  var s=sun(mid+12*HOUR, lat, lon);
  var eve=Math.min(mid+18*HOUR, s.sunset-15*MIN);     // start warming at 6pm (earlier only where the sun sets before ~6:15)
  var morn=Math.max(mid+8*HOUR, s.sunrise+30*MIN);    // fully day again
  if(now<s.dawn) return {dark:true, warm:0, next:s.dawn};
  if(now<s.sunrise) return {dark:false, warm:1, next:s.sunrise};
  if(now<morn) return {dark:false, warm:1-clamp((now-s.sunrise)/(morn-s.sunrise)), next:morn};
  if(now<eve) return {dark:false, warm:0, next:eve};
  if(now<s.sunset) return {dark:false, warm:clamp((now-eve)/(s.sunset-eve)), next:s.sunset};
  if(now<s.dusk) return {dark:false, warm:1, next:s.dusk};
  var tomorrow=sun(mid+DAY+12*HOUR, lat, lon);
  return {dark:true, warm:0, next:tomorrow.dawn};
}

// The knob's red mark is an hour hand: 0deg at 12 o'clock, 30deg per hour, creeping with the minutes.
function hourAngle(now){
  var d=new Date(now);
  return ((d.getHours()%12)*60+d.getMinutes())/2;
}

function read(k){ try{ return JSON.parse(localStorage.getItem(k)||"null"); }catch(e){ return null; } }

// The clock alone (no override), at the device's location if known, else the studio's.
function clock(now){
  var pos=read(POS)||HOME;
  return phase(now, pos.lat, pos.lon, -new Date(now).getTimezoneOffset());
}

// When the clock next switches between night and not-night. A click holds until then: by that time the clock
// has caught up with the choice, so automatic mode carries on without a jump.
function nextFlip(now){
  var c=clock(now), t=c.next;
  for(var i=0;i<8;i++){ var p=clock(t); if(p.dark!==c.dark) return t; t=p.next; }
  return now+DAY;
}

// The clock's answer, unless a click overrode it and that override hasn't run out yet.
function resolve(now){
  now=now||Date.now();
  var p=clock(now);
  var o=read(KEY);
  if(o && (o.theme==="light"||o.theme==="dark") && o.until>now)
    return {dark:o.theme==="dark", warm:0, angle:hourAngle(now), next:o.until, manual:true};
  return {dark:p.dark, warm:p.warm, angle:hourAngle(now), next:p.next, manual:false};
}

function apply(r){
  var d=document.documentElement;
  d.classList.toggle("dark", r.dark);
  d.style.colorScheme=r.dark?"dark":"light";
  d.style.setProperty("--warm", String(Math.round(r.warm*1000)/1000));
}

window.__vdTheme={sun:sun, phase:phase, hourAngle:hourAngle, clock:clock, nextFlip:nextFlip, resolve:resolve, apply:apply, KEY:KEY, POS:POS};
})();`;

/** Inline in <head>: set the theme (and the knob's angle) before anything paints. */
export const THEME_BOOT_SCRIPT = `${THEME_CORE}try{var r=window.__vdTheme.resolve();window.__vdTheme.apply(r);document.documentElement.style.setProperty("--knob-angle",r.angle+"deg");}catch(e){}`;

export type ThemeState = {
  dark: boolean;
  warm: number;
  /** Where the knob's red mark points: the hour, like a clock's hour hand. */
  angle: number;
  next: number;
  manual: boolean;
};

type Core = {
  sun: (
    t: number,
    lat: number,
    lon: number,
  ) => { sunrise: number; sunset: number; dawn: number; dusk: number };
  phase: (
    now: number,
    lat: number,
    lon: number,
    offsetMin: number,
  ) => Omit<ThemeState, "manual" | "angle">;
  /** The hour hand: degrees clockwise from 12 o'clock for this local time. */
  hourAngle: (now: number) => number;
  clock: (now: number) => Omit<ThemeState, "manual" | "angle">;
  nextFlip: (now: number) => number;
  resolve: (now?: number) => ThemeState;
  apply: (r: Pick<ThemeState, "dark" | "warm">) => void;
  KEY: string;
  POS: string;
};

/** The shared engine (installed by the boot script; installed here too if that somehow didn't run). */
export function themeCore(): Core {
  const w = window as unknown as { __vdTheme?: Core };
  if (!w.__vdTheme) new Function(THEME_CORE)();
  return w.__vdTheme!;
}
