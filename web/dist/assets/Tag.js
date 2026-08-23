import{n as e}from"./axios.js";import{A as t,C as n,E as r,S as i,U as a,W as o,it as s,nt as c,st as l,w as u}from"./vue-core.js";import{$ as d,J as f,Q as p,Y as m,Z as h,a as g,d as _,et as v,i as y,m as b,o as x,r as S,y as C}from"./Icon.js";import{P as w,R as T,U as E,ot as D,x as O,y as k}from"./Card.js";import{t as A}from"./create-injection-key.js";import{I as j}from"./index.js";function M(t){let{textColor2:n,primaryColorHover:r,primaryColorPressed:i,primaryColor:a,infoColor:o,successColor:s,warningColor:c,errorColor:l,baseColor:u,borderColor:d,opacityDisabled:f,tagColor:p,closeIconColor:m,closeIconColorHover:h,closeIconColorPressed:g,borderRadiusSmall:_,fontSizeMini:v,fontSizeTiny:y,fontSizeSmall:b,fontSizeMedium:S,heightMini:C,heightTiny:w,heightSmall:T,heightMedium:E,closeColorHover:D,closeColorPressed:O,buttonColor2Hover:k,buttonColor2Pressed:A,fontWeightStrong:M}=t;return e(e({},j),{},{closeBorderRadius:_,heightTiny:C,heightSmall:w,heightMedium:T,heightLarge:E,borderRadius:_,opacityDisabled:f,fontSizeTiny:v,fontSizeSmall:y,fontSizeMedium:b,fontSizeLarge:S,fontWeightStrong:M,textColorCheckable:n,textColorHoverCheckable:n,textColorPressedCheckable:n,textColorChecked:u,colorCheckable:`#0000`,colorHoverCheckable:k,colorPressedCheckable:A,colorChecked:a,colorCheckedHover:r,colorCheckedPressed:i,border:`1px solid ${d}`,textColor:n,color:p,colorBordered:`rgb(250, 250, 252)`,closeIconColor:m,closeIconColorHover:h,closeIconColorPressed:g,closeColorHover:D,closeColorPressed:O,borderPrimary:`1px solid ${x(a,{alpha:.3})}`,textColorPrimary:a,colorPrimary:x(a,{alpha:.12}),colorBorderedPrimary:x(a,{alpha:.1}),closeIconColorPrimary:a,closeIconColorHoverPrimary:a,closeIconColorPressedPrimary:a,closeColorHoverPrimary:x(a,{alpha:.12}),closeColorPressedPrimary:x(a,{alpha:.18}),borderInfo:`1px solid ${x(o,{alpha:.3})}`,textColorInfo:o,colorInfo:x(o,{alpha:.12}),colorBorderedInfo:x(o,{alpha:.1}),closeIconColorInfo:o,closeIconColorHoverInfo:o,closeIconColorPressedInfo:o,closeColorHoverInfo:x(o,{alpha:.12}),closeColorPressedInfo:x(o,{alpha:.18}),borderSuccess:`1px solid ${x(s,{alpha:.3})}`,textColorSuccess:s,colorSuccess:x(s,{alpha:.12}),colorBorderedSuccess:x(s,{alpha:.1}),closeIconColorSuccess:s,closeIconColorHoverSuccess:s,closeIconColorPressedSuccess:s,closeColorHoverSuccess:x(s,{alpha:.12}),closeColorPressedSuccess:x(s,{alpha:.18}),borderWarning:`1px solid ${x(c,{alpha:.35})}`,textColorWarning:c,colorWarning:x(c,{alpha:.15}),colorBorderedWarning:x(c,{alpha:.12}),closeIconColorWarning:c,closeIconColorHoverWarning:c,closeIconColorPressedWarning:c,closeColorHoverWarning:x(c,{alpha:.12}),closeColorPressedWarning:x(c,{alpha:.18}),borderError:`1px solid ${x(l,{alpha:.23})}`,textColorError:l,colorError:x(l,{alpha:.1}),colorBorderedError:x(l,{alpha:.08}),closeIconColorError:l,closeIconColorHoverError:l,closeIconColorPressedError:l,closeColorHoverError:x(l,{alpha:.12}),closeColorPressedError:x(l,{alpha:.18})})}var N={name:`Tag`,common:g,self:M},P={color:Object,type:{type:String,default:`default`},round:Boolean,size:String,closable:Boolean,disabled:{type:Boolean,default:void 0}},F=m(`tag`,`
 --n-close-margin: var(--n-close-margin-top) var(--n-close-margin-right) var(--n-close-margin-bottom) var(--n-close-margin-left);
 white-space: nowrap;
 position: relative;
 box-sizing: border-box;
 cursor: default;
 display: inline-flex;
 align-items: center;
 flex-wrap: nowrap;
 padding: var(--n-padding);
 border-radius: var(--n-border-radius);
 color: var(--n-text-color);
 background-color: var(--n-color);
 transition: 
 border-color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 line-height: 1;
 height: var(--n-height);
 font-size: var(--n-font-size);
`,[p(`strong`,`
 font-weight: var(--n-font-weight-strong);
 `),h(`border`,`
 pointer-events: none;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 border-radius: inherit;
 border: var(--n-border);
 transition: border-color .3s var(--n-bezier);
 `),h(`icon`,`
 display: flex;
 margin: 0 4px 0 0;
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 font-size: var(--n-avatar-size-override);
 `),h(`avatar`,`
 display: flex;
 margin: 0 6px 0 0;
 `),h(`close`,`
 margin: var(--n-close-margin);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `),p(`round`,`
 padding: 0 calc(var(--n-height) / 3);
 border-radius: calc(var(--n-height) / 2);
 `,[h(`icon`,`
 margin: 0 4px 0 calc((var(--n-height) - 8px) / -2);
 `),h(`avatar`,`
 margin: 0 6px 0 calc((var(--n-height) - 8px) / -2);
 `),p(`closable`,`
 padding: 0 calc(var(--n-height) / 4) 0 calc(var(--n-height) / 3);
 `)]),p(`icon, avatar`,[p(`round`,`
 padding: 0 calc(var(--n-height) / 3) 0 calc(var(--n-height) / 2);
 `)]),p(`disabled`,`
 cursor: not-allowed !important;
 opacity: var(--n-opacity-disabled);
 `),p(`checkable`,`
 cursor: pointer;
 box-shadow: none;
 color: var(--n-text-color-checkable);
 background-color: var(--n-color-checkable);
 `,[d(`disabled`,[f(`&:hover`,`background-color: var(--n-color-hover-checkable);`,[d(`checked`,`color: var(--n-text-color-hover-checkable);`)]),f(`&:active`,`background-color: var(--n-color-pressed-checkable);`,[d(`checked`,`color: var(--n-text-color-pressed-checkable);`)])]),p(`checked`,`
 color: var(--n-text-color-checked);
 background-color: var(--n-color-checked);
 `,[d(`disabled`,[f(`&:hover`,`background-color: var(--n-color-checked-hover);`),f(`&:active`,`background-color: var(--n-color-checked-pressed);`)])])])]),I=[`onClick`,`onMouseenter`,`onMouseleave`],L=e(e(e({},S.props),P),{},{bordered:{type:Boolean,default:void 0},checked:Boolean,checkable:Boolean,strong:Boolean,triggerClickOnClose:Boolean,onClose:[Array,Function],onMouseenter:Function,onMouseleave:Function,"onUpdate:checked":Function,onUpdateChecked:Function,internalCloseFocusable:{type:Boolean,default:!0},internalCloseIsButtonTag:{type:Boolean,default:!0},onCheckedChange:Function}),R=A(`n-tag`),z=t({name:`Tag`,props:L,slots:Object,setup(t){let n=c(null),{mergedBorderedRef:r,mergedClsPrefixRef:a,inlineThemeDisabled:l,mergedRtlRef:u,mergedComponentPropsRef:d}=C(t),f=i(()=>{var e;return t.size||(d==null||(e=d.value)==null||(e=e.Tag)==null?void 0:e.size)||`medium`}),p=S(`Tag`,`-tag`,F,N,t,a);o(R,{roundRef:s(t,`round`)});function m(){if(!t.disabled&&t.checkable){let{checked:e,onCheckedChange:n,onUpdateChecked:r,"onUpdate:checked":i}=t;r&&r(!e),i&&i(!e),n&&n(!e)}}function h(e){if(t.triggerClickOnClose||e.stopPropagation(),!t.disabled){let{onClose:n}=t;n&&E(n,e)}}let g={setTextContent(e){let{value:t}=n;t&&(t.textContent=e)}},_=w(`Tag`,u,a),b=i(()=>{let{type:e,color:{color:n,textColor:i}={}}=t,a=f.value,{common:{cubicBezierEaseInOut:o},self:{padding:s,closeMargin:c,borderRadius:l,opacityDisabled:u,textColorCheckable:d,textColorHoverCheckable:m,textColorPressedCheckable:h,textColorChecked:g,colorCheckable:_,colorHoverCheckable:y,colorPressedCheckable:b,colorChecked:x,colorCheckedHover:S,colorCheckedPressed:C,closeBorderRadius:w,fontWeightStrong:T,[v(`colorBordered`,e)]:E,[v(`closeSize`,a)]:O,[v(`closeIconSize`,a)]:k,[v(`fontSize`,a)]:A,[v(`height`,a)]:j,[v(`color`,e)]:M,[v(`textColor`,e)]:N,[v(`border`,e)]:P,[v(`closeIconColor`,e)]:F,[v(`closeIconColorHover`,e)]:I,[v(`closeIconColorPressed`,e)]:L,[v(`closeColorHover`,e)]:R,[v(`closeColorPressed`,e)]:z}}=p.value,B=D(c);return{"--n-font-weight-strong":T,"--n-avatar-size-override":`calc(${j} - 8px)`,"--n-bezier":o,"--n-border-radius":l,"--n-border":P,"--n-close-icon-size":k,"--n-close-color-pressed":z,"--n-close-color-hover":R,"--n-close-border-radius":w,"--n-close-icon-color":F,"--n-close-icon-color-hover":I,"--n-close-icon-color-pressed":L,"--n-close-icon-color-disabled":F,"--n-close-margin-top":B.top,"--n-close-margin-right":B.right,"--n-close-margin-bottom":B.bottom,"--n-close-margin-left":B.left,"--n-close-size":O,"--n-color":n||(r.value?E:M),"--n-color-checkable":_,"--n-color-checked":x,"--n-color-checked-hover":S,"--n-color-checked-pressed":C,"--n-color-hover-checkable":y,"--n-color-pressed-checkable":b,"--n-font-size":A,"--n-height":j,"--n-opacity-disabled":u,"--n-padding":s,"--n-text-color":i||N,"--n-text-color-checkable":d,"--n-text-color-checked":g,"--n-text-color-hover-checkable":m,"--n-text-color-pressed-checkable":h}}),x=l?y(`tag`,i(()=>{let e=``,{type:n,color:{color:i,textColor:a}={}}=t;return e+=n[0],e+=f.value[0],i&&(e+=`a${O(i)}`),a&&(e+=`b${O(a)}`),r.value&&(e+=`c`),e}),b,t):void 0;return e(e({},g),{},{rtlEnabled:_,mergedClsPrefix:a,contentRef:n,mergedBordered:r,handleClick:m,handleCloseClick:h,cssVars:l?void 0:b,themeClass:x==null?void 0:x.themeClass,onRender:x==null?void 0:x.onRender})},render(){let{mergedClsPrefix:e,rtlEnabled:t,closable:i,color:{borderColor:o}={},round:s,onRender:c,$slots:d}=this;c==null||c();let f=T(d.avatar,t=>t&&(a(),r(`div`,{class:_(`${e}-tag__avatar`)},[b(()=>t)],2))),p=T(d.icon,t=>t&&(a(),r(`div`,{class:_(`${e}-tag__icon`)},[b(()=>t)],2)));return a(),r(`div`,{class:_([`${e}-tag`,this.themeClass,{[`${e}-tag--rtl`]:t,[`${e}-tag--strong`]:this.strong,[`${e}-tag--disabled`]:this.disabled,[`${e}-tag--checkable`]:this.checkable,[`${e}-tag--checked`]:this.checkable&&this.checked,[`${e}-tag--round`]:s,[`${e}-tag--avatar`]:f,[`${e}-tag--icon`]:p,[`${e}-tag--closable`]:i}]),style:l(this.cssVars),onClick:this.handleClick,onMouseenter:this.onMouseenter,onMouseleave:this.onMouseleave},[b(()=>p||f),n(`span`,{class:_(`${e}-tag__content`),ref:`contentRef`},[b(()=>{var e,t;return(e=(t=this.$slots).default)==null?void 0:e.call(t)})],2),!this.checkable&&i?(a(),u(k,{key:0,clsPrefix:e,class:_(`${e}-tag__close`),disabled:this.disabled,onClick:this.handleCloseClick,focusable:this.internalCloseFocusable,round:s,isButtonTag:this.internalCloseIsButtonTag,absolute:!0},null,8,[`clsPrefix`,`class`,`disabled`,`onClick`,`focusable`,`round`,`isButtonTag`])):b(()=>null),!this.checkable&&this.mergedBordered?(a(),r(`div`,{key:2,class:_(`${e}-tag__border`),style:l({borderColor:o})},null,6)):b(()=>null)],46,I)}});export{R as n,z as t};