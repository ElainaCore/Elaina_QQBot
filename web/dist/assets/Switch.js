import{n as e}from"./axios.js";import{A as t,C as n,E as r,F as i,S as a,U as o,it as s,nt as c,st as l,w as u}from"./vue-core.js";import{$ as d,J as f,Q as p,Y as m,Z as h,a as g,d as _,et as v,i as y,m as b,o as x,r as S,y as C}from"./Icon.js";import{F as w,R as T,U as E,_ as D,at as O,f as k,h as A,m as j,st as M}from"./Card.js";import{t as N}from"./use-merged-state.js";import{i as P}from"./index.js";function F(t){let{primaryColor:n,opacityDisabled:r,borderRadius:i,textColor3:a}=t;return e(e({},P),{},{iconColor:a,textColor:`white`,loadingColor:n,opacityDisabled:r,railColor:`rgba(0, 0, 0, .14)`,railColorActive:n,buttonBoxShadow:`0 1px 4px 0 rgba(0, 0, 0, 0.3), inset 0 0 1px 0 rgba(0, 0, 0, 0.05)`,buttonColor:`#FFF`,railBorderRadiusSmall:i,railBorderRadiusMedium:i,railBorderRadiusLarge:i,buttonBorderRadiusSmall:i,buttonBorderRadiusMedium:i,buttonBorderRadiusLarge:i,boxShadowFocus:`0 0 0 2px ${x(n,{alpha:.2})}`})}var I={name:`Switch`,common:g,self:F},L=m(`switch`,`
 height: var(--n-height);
 min-width: var(--n-width);
 vertical-align: middle;
 user-select: none;
 -webkit-user-select: none;
 display: inline-flex;
 outline: none;
 justify-content: center;
 align-items: center;
`,[h(`children-placeholder`,`
 height: var(--n-rail-height);
 display: flex;
 flex-direction: column;
 overflow: hidden;
 pointer-events: none;
 visibility: hidden;
 `),h(`rail-placeholder`,`
 display: flex;
 flex-wrap: none;
 `),h(`button-placeholder`,`
 width: calc(1.75 * var(--n-rail-height));
 height: var(--n-rail-height);
 `),m(`base-loading`,`
 position: absolute;
 top: 50%;
 left: 50%;
 transform: translateX(-50%) translateY(-50%);
 font-size: calc(var(--n-button-width) - 4px);
 color: var(--n-loading-color);
 transition: color .3s var(--n-bezier);
 `,[j({left:`50%`,top:`50%`,originalTransform:`translateX(-50%) translateY(-50%)`})]),h(`checked, unchecked`,`
 transition: color .3s var(--n-bezier);
 color: var(--n-text-color);
 box-sizing: border-box;
 position: absolute;
 white-space: nowrap;
 top: 0;
 bottom: 0;
 display: flex;
 align-items: center;
 line-height: 1;
 `),h(`checked`,`
 right: 0;
 padding-right: calc(1.25 * var(--n-rail-height) - var(--n-offset));
 `),h(`unchecked`,`
 left: 0;
 justify-content: flex-end;
 padding-left: calc(1.25 * var(--n-rail-height) - var(--n-offset));
 `),f(`&:focus`,[h(`rail`,`
 box-shadow: var(--n-box-shadow-focus);
 `)]),p(`round`,[h(`rail`,`border-radius: calc(var(--n-rail-height) / 2);`,[h(`button`,`border-radius: calc(var(--n-button-height) / 2);`)])]),d(`disabled`,[d(`icon`,[p(`rubber-band`,[p(`pressed`,[h(`rail`,[h(`button`,`max-width: var(--n-button-width-pressed);`)])]),h(`rail`,[f(`&:active`,[h(`button`,`max-width: var(--n-button-width-pressed);`)])]),p(`active`,[p(`pressed`,[h(`rail`,[h(`button`,`left: calc(100% - var(--n-offset) - var(--n-button-width-pressed));`)])]),h(`rail`,[f(`&:active`,[h(`button`,`left: calc(100% - var(--n-offset) - var(--n-button-width-pressed));`)])])])])])]),p(`active`,[h(`rail`,[h(`button`,`left: calc(100% - var(--n-button-width) - var(--n-offset))`)])]),h(`rail`,`
 overflow: hidden;
 height: var(--n-rail-height);
 min-width: var(--n-rail-width);
 border-radius: var(--n-rail-border-radius);
 cursor: pointer;
 position: relative;
 transition:
 opacity .3s var(--n-bezier),
 background .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 background-color: var(--n-rail-color);
 `,[h(`button-icon`,`
 color: var(--n-icon-color);
 transition: color .3s var(--n-bezier);
 font-size: calc(var(--n-button-height) - 4px);
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 display: flex;
 justify-content: center;
 align-items: center;
 line-height: 1;
 `,[j()]),h(`button`,`
 align-items: center; 
 top: var(--n-offset);
 left: var(--n-offset);
 height: var(--n-button-height);
 width: var(--n-button-width-pressed);
 max-width: var(--n-button-width);
 border-radius: var(--n-button-border-radius);
 background-color: var(--n-button-color);
 box-shadow: var(--n-button-box-shadow);
 box-sizing: border-box;
 cursor: inherit;
 content: "";
 position: absolute;
 transition:
 background-color .3s var(--n-bezier),
 left .3s var(--n-bezier),
 opacity .3s var(--n-bezier),
 max-width .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 `)]),p(`active`,[h(`rail`,`background-color: var(--n-rail-color-active);`)]),p(`loading`,[h(`rail`,`
 cursor: wait;
 `)]),p(`disabled`,[h(`rail`,`
 cursor: not-allowed;
 opacity: .5;
 `)])]),R=[`aria-checked`,`tabindex`,`onClick`,`onFocus`,`onBlur`,`onKeyup`,`onKeydown`],z=e(e({},S.props),{},{size:String,value:{type:[String,Number,Boolean],default:void 0},loading:Boolean,defaultValue:{type:[String,Number,Boolean],default:!1},disabled:{type:Boolean,default:void 0},round:{type:Boolean,default:!0},"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],checkedValue:{type:[String,Number,Boolean],default:!0},uncheckedValue:{type:[String,Number,Boolean],default:!1},railStyle:Function,rubberBand:{type:Boolean,default:!0},spinProps:Object,onChange:[Function,Array]}),B,V=t({name:`Switch`,props:z,slots:Object,setup(e){B===void 0&&(B=typeof CSS<`u`?CSS.supports!==void 0&&CSS.supports(`width`,`max(1px)`):!0);let{mergedClsPrefixRef:t,inlineThemeDisabled:n,mergedComponentPropsRef:r}=C(e),i=S(`Switch`,`-switch`,L,I,e,t),o=D(e,{mergedSize(t){var n;return e.size===void 0?t?t.mergedSize.value:(r==null||(n=r.value)==null||(n=n.Switch)==null?void 0:n.size)||`medium`:e.size}}),{mergedSizeRef:l,mergedDisabledRef:u}=o,d=c(e.defaultValue),f=s(e,`value`),p=N(f,d),m=a(()=>p.value===e.checkedValue),h=c(!1),g=c(!1),_=a(()=>{let{railStyle:t}=e;if(t)return t({focused:g.value,checked:m.value})});function b(t){let{"onUpdate:value":n,onChange:r,onUpdateValue:i}=e,{nTriggerFormInput:a,nTriggerFormChange:s}=o;n&&E(n,t),i&&E(i,t),r&&E(r,t),d.value=t,a(),s()}function x(){let{nTriggerFormFocus:e}=o;e()}function w(){let{nTriggerFormBlur:e}=o;e()}function T(){e.loading||u.value||(p.value===e.checkedValue?b(e.uncheckedValue):b(e.checkedValue))}function k(){g.value=!0,x()}function A(){g.value=!1,w(),h.value=!1}function j(t){e.loading||u.value||t.key===` `&&(p.value===e.checkedValue?b(e.uncheckedValue):b(e.checkedValue),h.value=!1)}function P(t){e.loading||u.value||t.key===` `&&(t.preventDefault(),h.value=!0)}let F=a(()=>{let{value:e}=l,{self:{opacityDisabled:t,railColor:n,railColorActive:r,buttonBoxShadow:a,buttonColor:o,boxShadowFocus:s,loadingColor:c,textColor:u,iconColor:d,[v(`buttonHeight`,e)]:f,[v(`buttonWidth`,e)]:p,[v(`buttonWidthPressed`,e)]:m,[v(`railHeight`,e)]:h,[v(`railWidth`,e)]:g,[v(`railBorderRadius`,e)]:_,[v(`buttonBorderRadius`,e)]:y},common:{cubicBezierEaseInOut:b}}=i.value,x,S,C;return B?(x=`calc((${h} - ${f}) / 2)`,S=`max(${h}, ${f})`,C=`max(${g}, calc(${g} + ${f} - ${h}))`):(x=M((O(h)-O(f))/2),S=M(Math.max(O(h),O(f))),C=O(h)>O(f)?g:M(O(g)+O(f)-O(h))),{"--n-bezier":b,"--n-button-border-radius":y,"--n-button-box-shadow":a,"--n-button-color":o,"--n-button-width":p,"--n-button-width-pressed":m,"--n-button-height":f,"--n-height":S,"--n-offset":x,"--n-opacity-disabled":t,"--n-rail-border-radius":_,"--n-rail-color":n,"--n-rail-color-active":r,"--n-rail-height":h,"--n-rail-width":g,"--n-width":C,"--n-box-shadow-focus":s,"--n-loading-color":c,"--n-text-color":u,"--n-icon-color":d}}),R=n?y(`switch`,a(()=>l.value[0]),F,e):void 0;return{handleClick:T,handleBlur:A,handleFocus:k,handleKeyup:j,handleKeydown:P,mergedRailStyle:_,pressed:h,mergedClsPrefix:t,mergedValue:p,checked:m,mergedDisabled:u,cssVars:n?void 0:F,themeClass:R==null?void 0:R.themeClass,onRender:R==null?void 0:R.onRender}},render(){let{mergedClsPrefix:e,mergedDisabled:t,checked:a,mergedRailStyle:s,onRender:c,$slots:d}=this;c==null||c();let{checked:f,unchecked:p,icon:m,"checked-icon":h,"unchecked-icon":g}=d,v=!(w(m)&&w(h)&&w(g));return o(),r(`div`,{role:`switch`,"aria-checked":a,class:_([`${e}-switch`,this.themeClass,v&&`${e}-switch--icon`,a&&`${e}-switch--active`,t&&`${e}-switch--disabled`,this.round&&`${e}-switch--round`,this.loading&&`${e}-switch--loading`,this.pressed&&`${e}-switch--pressed`,this.rubberBand&&`${e}-switch--rubber-band`]),tabindex:this.mergedDisabled?void 0:0,style:l(this.cssVars),onClick:this.handleClick,onFocus:this.handleFocus,onBlur:this.handleBlur,onKeyup:this.handleKeyup,onKeydown:this.handleKeydown},[n(`div`,{class:_(`${e}-switch__rail`),"aria-hidden":`true`,style:l(s)},[b(()=>T(f,t=>T(p,i=>t||i?(o(),r(`div`,{key:4,"aria-hidden":!0,class:_(`${e}-switch__children-placeholder`)},[n(`div`,{class:_(`${e}-switch__rail-placeholder`)},[n(`div`,{class:_(`${e}-switch__button-placeholder`)},null,2),b(()=>t)],2),n(`div`,{class:_(`${e}-switch__rail-placeholder`)},[n(`div`,{class:_(`${e}-switch__button-placeholder`)},null,2),b(()=>i)],2)],2)):null))),n(`div`,{class:_(`${e}-switch__button`)},[b(()=>T(m,t=>T(h,n=>T(g,a=>(o(),u(A,null,{default:()=>this.loading?(o(),u(k,i({key:`loading`,clsPrefix:e,strokeWidth:20},this.spinProps),null,16,[`clsPrefix`])):this.checked&&(n||t)?(o(),r(`div`,{class:_(`${e}-switch__button-icon`),key:n?`checked-icon`:`icon`},[b(()=>n||t)],2)):!this.checked&&(a||t)?(o(),r(`div`,{class:_(`${e}-switch__button-icon`),key:a?`unchecked-icon`:`icon`},[b(()=>a||t)],2)):null},1024)))))),b(()=>T(f,t=>t&&(o(),r(`div`,{key:`checked`,class:_(`${e}-switch__checked`)},[b(()=>t)],2)))),b(()=>T(p,t=>t&&(o(),r(`div`,{key:`unchecked`,class:_(`${e}-switch__unchecked`)},[b(()=>t)],2))))],2)],6)],46,R)}});export{V as t};