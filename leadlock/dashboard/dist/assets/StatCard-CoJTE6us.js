import{c as n,j as e}from"./index-BHeaMpcx.js";/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const g=n("ArrowDown",[["path",{d:"M12 5v14",key:"s699le"}],["path",{d:"m19 12-7 7-7-7",key:"1idqje"}]]);/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const b=n("ArrowUp",[["path",{d:"m5 12 7-7 7 7",key:"hav0vg"}],["path",{d:"M12 19V5",key:"x0mq9r"}]]);/**
 * @license lucide-react v0.460.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=n("Minus",[["path",{d:"M5 12h14",key:"1ays0h"}]]),l={brand:{badge:"bg-orange-50 text-orange-600",accent:"bg-orange-500",deltaUp:"text-emerald-600",deltaDown:"text-red-500"},green:{badge:"bg-emerald-50 text-emerald-600",accent:"bg-emerald-500",deltaUp:"text-emerald-600",deltaDown:"text-red-500"},yellow:{badge:"bg-amber-50 text-amber-600",accent:"bg-amber-500",deltaUp:"text-emerald-600",deltaDown:"text-red-500"},red:{badge:"bg-red-50 text-red-600",accent:"bg-red-500",deltaUp:"text-emerald-600",deltaDown:"text-red-500"},blue:{badge:"bg-blue-50 text-blue-600",accent:"bg-blue-500",deltaUp:"text-emerald-600",deltaDown:"text-red-500"},purple:{badge:"bg-purple-50 text-purple-600",accent:"bg-purple-500",deltaUp:"text-emerald-600",deltaDown:"text-red-500"}};function w({label:x,value:i,delta:t,deltaLabel:a,icon:o,color:m="brand"}){const r=l[m]||l.brand,s=t!==void 0&&t>0,d=t!==void 0&&t<0,p=s?b:d?g:h,c=s?r.deltaUp:d?r.deltaDown:"text-gray-400";return e.jsxs("div",{className:"bg-white border border-gray-200/50 rounded-2xl p-5 shadow-card relative overflow-hidden group transition-shadow duration-200 hover:shadow-card-hover",children:[e.jsx("div",{className:`absolute top-0 left-0 right-0 h-[2px] ${r.accent} opacity-60`}),e.jsxs("div",{className:"flex items-start justify-between",children:[e.jsx("p",{className:"text-[11px] font-semibold text-gray-400 uppercase tracking-widest",children:x}),o&&e.jsx("div",{className:`w-9 h-9 rounded-xl flex items-center justify-center ${r.badge}`,children:e.jsx(o,{className:"w-[18px] h-[18px]",strokeWidth:1.75})})]}),e.jsx("p",{className:"metric-value text-metric text-gray-900 mt-3",children:i}),t!==void 0&&e.jsxs("div",{className:"flex items-center gap-1.5 mt-3",children:[e.jsxs("div",{className:`flex items-center gap-0.5 px-1.5 py-0.5 rounded-md ${s?"bg-emerald-50":d?"bg-red-50":"bg-gray-50"}`,children:[e.jsx(p,{className:`w-3 h-3 ${c}`,strokeWidth:2.5}),e.jsxs("span",{className:`text-xs font-semibold ${c}`,children:[Math.abs(t),"%"]})]}),a&&e.jsx("span",{className:"text-[11px] text-gray-400 font-medium",children:a})]}),t===void 0&&a&&e.jsx("div",{className:"mt-3",children:e.jsx("span",{className:"text-[11px] text-gray-400 font-medium",children:a})})]})}export{w as S};
