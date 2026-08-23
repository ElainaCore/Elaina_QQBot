import{n as e}from"./axios.js";import{A as t,B as n,C as r,E as i,F as a,I as o,K as s,L as c,M as l,N as u,Q as d,S as f,U as p,V as m,W as h,X as g,Y as _,c as v,it as y,k as b,m as x,nt as S,st as C,v as w,w as T,z as E}from"./vue-core.js";import{$ as D,J as O,Q as k,Y as A,Z as j,d as M,et as N,f as P,g as F,i as ee,m as I,r as L,t as R,u as z,y as te}from"./Icon.js";import{E as B,I as V,M as ne,N as H,P as re,R as U,S as ie,T as W,U as G,W as K,_ as ae,at as oe,ct as se,f as ce,k as le,ot as q,p as J,q as Y,st as X}from"./Card.js";import{t as ue}from"./use-locale.js";import{a as de,c as fe,d as pe,f as me,i as he,m as ge,o as _e,p as ve,s as ye,t as be,u as Z}from"./Popover.js";import{t as xe}from"./Empty.js";import{t as Se}from"./use-merged-state.js";import{t as Ce}from"./Tag.js";import{n as we}from"./Input.js";import{C as Te,D as Ee,E as De,O as Q,R as Oe,S as ke,a as Ae,y as je}from"./index.js";function Me(e,t){let{target:n}=e;for(;n;){if(n.dataset&&n.dataset[t]!==void 0)return!0;n=n.parentElement}return!1}function Ne(e){return e&-e}var Pe=class{constructor(e,t){this.l=e,this.min=t;let n=Array(e+1);for(let t=0;t<e+1;++t)n[t]=0;this.ft=n}add(e,t){if(t===0)return;let{l:n,ft:r}=this;for(e+=1;e<=n;)r[e]+=t,e+=Ne(e)}get(e){return this.sum(e+1)-this.sum(e)}sum(e){if(e===void 0&&(e=this.l),e<=0)return 0;let{ft:t,min:n,l:r}=this;if(e>r)throw Error("[FinweckTree.sum]: `i` is larger than length.");let i=e*n;for(;e>0;)i+=t[e],e-=Ne(e);return i}getBound(e){let t=0,n=this.l;for(;n>t;){let r=Math.floor((t+n)/2),i=this.sum(r);if(i>e){n=r;continue}if(i<e){if(t===r)return this.sum(t+1)<=e?t+1:r;t=r}else return r}return t}},Fe;function Ie(){return typeof document>`u`?!1:(Fe===void 0&&(Fe=`matchMedia`in window&&window.matchMedia(`(pointer:coarse)`).matches),Fe)}var Le;function Re(){return typeof document>`u`?1:(Le===void 0&&(Le=`chrome`in window?window.devicePixelRatio:1),Le)}var ze=`VVirtualListXScroll`;function Be({columnsRef:e,renderColRef:t,renderItemWithColsRef:n}){let r=S(0),i=S(0),a=f(()=>{let t=e.value;if(t.length===0)return null;let n=new Pe(t.length,0);return t.forEach((e,t)=>{n.add(t,e.width)}),n}),o=Y(()=>{let e=a.value;return e===null?0:Math.max(e.getBound(i.value)-1,0)}),s=e=>{let t=a.value;return t===null?0:t.sum(e)},c=Y(()=>{let t=a.value;return t===null?0:Math.min(t.getBound(i.value+r.value)+1,e.value.length-1)});return h(ze,{startIndexRef:o,endIndexRef:c,columnsRef:e,renderColRef:t,renderItemWithColsRef:n,getLeft:s}),{listWidthRef:r,scrollLeftRef:i}}var Ve=t({name:`VirtualListRow`,props:{index:{type:Number,required:!0},item:{type:Object,required:!0}},setup(){let{startIndexRef:e,endIndexRef:t,columnsRef:n,getLeft:r,renderColRef:i,renderItemWithColsRef:a}=u(ze);return{startIndex:e,endIndex:t,columns:n,renderCol:i,renderItemWithCols:a,getLeft:r}},render(){let{startIndex:e,endIndex:t,columns:n,renderCol:r,renderItemWithCols:i,getLeft:a,item:o}=this;if(i!=null)return i({itemIndex:this.index,startColIndex:e,endColIndex:t,allColumns:n,item:o,getLeft:a});if(r!=null){let i=[];for(let s=e;s<=t;++s){let e=n[s];i.push(r({column:e,left:a(s),item:o}))}return i}return null}}),He=de(`.v-vl`,{maxHeight:`inherit`,height:`100%`,overflow:`auto`,minWidth:`1px`},[de(`&:not(.v-vl--show-scrollbar)`,{scrollbarWidth:`none`},[de(`&::-webkit-scrollbar, &::-webkit-scrollbar-track-piece, &::-webkit-scrollbar-thumb`,{width:0,height:0,display:`none`})])]),Ue=t({name:`VirtualList`,inheritAttrs:!1,props:{showScrollbar:{type:Boolean,default:!0},columns:{type:Array,default:()=>[]},renderCol:Function,renderItemWithCols:Function,items:{type:Array,default:()=>[]},itemSize:{type:Number,required:!0},itemResizable:Boolean,itemsStyle:[String,Object],visibleItemsTag:{type:[String,Object],default:`div`},visibleItemsProps:Object,ignoreItemResize:Boolean,onScroll:Function,onWheel:Function,onResize:Function,defaultScrollKey:[Number,String],defaultScrollIndex:Number,keyField:{type:String,default:`key`},paddingTop:{type:[Number,String],default:0},paddingBottom:{type:[Number,String],default:0}},setup(e){let t=F();He.mount({id:`vueuc/virtual-list`,head:!0,anchorMetaName:_e,ssr:t}),m(()=>{let{defaultScrollIndex:t,defaultScrollKey:n}=e;t==null?n!=null&&x({key:n}):x({index:t})});let r=!1,i=!1;c(()=>{if(r=!1,!i){i=!0;return}x({top:_.value,left:s.value})}),n(()=>{r=!0,i||(i=!0)});let a=Y(()=>{if(e.renderCol==null&&e.renderItemWithCols==null||e.columns.length===0)return;let t=0;return e.columns.forEach(e=>{t+=e.width}),t}),o=f(()=>{let t=new Map,{keyField:n}=e;return e.items.forEach((e,r)=>{t.set(e[n],r)}),t}),{scrollLeftRef:s,listWidthRef:l}=Be({columnsRef:y(e,`columns`),renderColRef:y(e,`renderCol`),renderItemWithColsRef:y(e,`renderItemWithCols`)}),u=S(null),d=S(void 0),p=new Map,h=f(()=>{let{items:t,itemSize:n,keyField:r}=e,i=new Pe(t.length,n);return t.forEach((e,t)=>{let n=e[r],a=p.get(n);a!==void 0&&i.add(t,a)}),i}),g=S(0),_=S(0),v=Y(()=>Math.max(h.value.getBound(_.value-oe(e.paddingTop))-1,0)),b=f(()=>{let{value:t}=d;if(t===void 0)return[];let{items:n,itemSize:r}=e,i=v.value,a=Math.min(i+Math.ceil(t/r+1),n.length-1),o=[];for(let e=i;e<=a;++e)o.push(n[e]);return o}),x=(e,t)=>{if(typeof e==`number`){E(e,t,`auto`);return}let{left:n,top:r,index:i,key:a,position:s,behavior:c,debounce:l=!0}=e;if(n!==void 0||r!==void 0)E(n,r,c);else if(i!==void 0)T(i,c,l);else if(a!==void 0){let e=o.value.get(a);e!==void 0&&T(e,c,l)}else s===`bottom`?E(0,9007199254740991,c):s===`top`&&E(0,0,c)},C,w=null;function T(t,n,r){let i=u.value;if(i==null)return;let{value:a}=h,o=a.sum(t)+oe(e.paddingTop);if(!r)i.scrollTo({left:0,top:o,behavior:n});else{C=t,w!==null&&window.clearTimeout(w),w=window.setTimeout(()=>{C=void 0,w=null},16);let{scrollTop:e,offsetHeight:r}=i;if(o>e){let s=a.get(t);o+s<=e+r||i.scrollTo({left:0,top:o+s-r,behavior:n})}else i.scrollTo({left:0,top:o,behavior:n})}}function E(e,t,n){let r=u.value;r!=null&&r.scrollTo({left:e,top:t,behavior:n})}function D(t,n){var i,a,s;if(r||e.ignoreItemResize||P(n.target))return;let{value:c}=h,l=o.value.get(t),d=c.get(l),f=(s=(a=(i=n.borderBoxSize)==null?void 0:i[0])==null?void 0:a.blockSize)==null?n.contentRect.height:s;if(f===d)return;f-e.itemSize===0?p.delete(t):p.set(t,f-e.itemSize);let m=f-d;if(m===0)return;c.add(l,m);let _=u.value;if(_!=null){if(C===void 0){let e=c.sum(l);_.scrollTop>e&&_.scrollBy(0,m)}else(l<C||l===C&&f+c.sum(l)>_.scrollTop+_.offsetHeight)&&_.scrollBy(0,m);N()}g.value++}let O=!Ie(),k=!1;function A(t){var n;(n=e.onScroll)==null||n.call(e,t),(!O||!k)&&N()}function j(t){var n;if((n=e.onWheel)==null||n.call(e,t),O){let e=u.value;if(e!=null){if(t.deltaX===0&&(e.scrollTop===0&&t.deltaY<=0||e.scrollTop+e.offsetHeight>=e.scrollHeight&&t.deltaY>=0))return;t.preventDefault(),e.scrollTop+=t.deltaY/Re(),e.scrollLeft+=t.deltaX/Re(),N(),k=!0,ge(()=>{k=!1})}}}function M(t){if(r||P(t.target))return;if(e.renderCol==null&&e.renderItemWithCols==null){if(t.contentRect.height===d.value)return}else if(t.contentRect.height===d.value&&t.contentRect.width===l.value)return;d.value=t.contentRect.height,l.value=t.contentRect.width;let{onResize:n}=e;n!==void 0&&n(t)}function N(){let{value:e}=u;e!=null&&(_.value=e.scrollTop,s.value=e.scrollLeft)}function P(e){let t=e;for(;t!==null;){if(t.style.display===`none`)return!0;t=t.parentElement}return!1}return{listHeight:d,listStyle:{overflow:`auto`},keyToIndex:o,itemsStyle:f(()=>{let{itemResizable:t}=e,n=X(h.value.sum());return g.value,[e.itemsStyle,{boxSizing:`content-box`,width:X(a.value),height:t?``:n,minHeight:t?n:``,paddingTop:X(e.paddingTop),paddingBottom:X(e.paddingBottom)}]}),visibleItemsStyle:f(()=>(g.value,{transform:`translateY(${X(h.value.sum(v.value))})`})),viewportItems:b,listElRef:u,itemsElRef:S(null),scrollTo:x,handleListResize:M,handleListScroll:A,handleListWheel:j,handleItemResize:D}},render(){let{itemResizable:e,keyField:t,keyToIndex:n,visibleItemsTag:r}=this;return l(W,{onResize:this.handleListResize},{default:()=>{var i,o;return l(`div`,a(this.$attrs,{class:[`v-vl`,this.showScrollbar&&`v-vl--show-scrollbar`],onScroll:this.handleListScroll,onWheel:this.handleListWheel,ref:`listElRef`}),[this.items.length===0?(o=(i=this.$slots).empty)==null?void 0:o.call(i):l(`div`,{ref:`itemsElRef`,class:`v-vl-items`,style:this.itemsStyle},[l(r,Object.assign({class:`v-vl-visible-items`,style:this.visibleItemsStyle},this.visibleItemsProps),{default:()=>{let{renderCol:r,renderItemWithCols:i}=this;return this.viewportItems.map(a=>{let o=a[t],s=n.get(o),c=r==null?void 0:l(Ve,{index:s,item:a}),u=i==null?void 0:l(Ve,{index:s,item:a}),d=this.$slots.default({item:a,renderedCols:c,renderedItemWithCols:u,index:s})[0];return e?l(W,{key:o,onResize:e=>this.handleItemResize(o,e)},{default:()=>d}):(d.key=o,d)})}})])])}})}}),$=`v-hidden`,We=de(`[v-hidden]`,{display:`none!important`}),Ge=t({name:`Overflow`,props:{getCounter:Function,getTail:Function,updateCounter:Function,onUpdateCount:Function,onUpdateOverflow:Function},setup(e,{slots:t}){let n=S(null),r=S(null);function i(i){let{value:a}=n,{getCounter:o,getTail:s}=e,c;if(c=o===void 0?r.value:o(),!a||!c)return;c.hasAttribute($)&&c.removeAttribute($);let{children:l}=a;if(i.showAllItemsBeforeCalculate)for(let e of l)e.hasAttribute($)&&e.removeAttribute($);let u=a.offsetWidth,d=[],f=t.tail?s==null?void 0:s():null,p=f?f.offsetWidth:0,m=!1,h=a.children.length-+!!t.tail;for(let t=0;t<h-1;++t){if(t<0)continue;let n=l[t];if(m){n.hasAttribute($)||n.setAttribute($,``);continue}n.hasAttribute($)&&n.removeAttribute($);let r=n.offsetWidth;if(p+=r,d[t]=r,p>u){let{updateCounter:n}=e;for(let r=t;r>=0;--r){let i=h-1-r;n===void 0?c.textContent=`${i}`:n(i);let a=c.offsetWidth;if(p-=d[r],p+a<=u||r===0){m=!0,t=r-1,f&&(t===-1?(f.style.maxWidth=`${u-a}px`,f.style.boxSizing=`border-box`):f.style.maxWidth=``);let{onUpdateCount:n}=e;n&&n(i);break}}}}let{onUpdateOverflow:g}=e;m?g!==void 0&&g(!0):(g!==void 0&&g(!1),c.setAttribute($,``))}let a=F();return We.mount({id:`vueuc/overflow`,head:!0,anchorMetaName:_e,ssr:a}),m(()=>i({showAllItemsBeforeCalculate:!1})),{selfRef:n,counterRef:r,sync:i}},render(){let{$slots:e}=this;return o(()=>this.sync({showAllItemsBeforeCalculate:!1})),l(`div`,{class:`v-overflow`,ref:`selfRef`},[s(e,`default`),e.counter?e.counter():l(`span`,{style:{display:`inline-block`},ref:`counterRef`}),e.tail?e.tail():null])}});function Ke(e){switch(typeof e){case`string`:return e||void 0;case`number`:return String(e);default:return}}function qe(e,t){t&&(m(()=>{let{value:n}=e;n&&B.registerHandler(n,t)}),_(e,(e,t)=>{t&&B.unregisterHandler(t)},{deep:!1}),E(()=>{let{value:t}=e;t&&B.unregisterHandler(t)}))}var Je=t({props:{onFocus:Function,onBlur:Function},setup(e){return()=>(()=>{let t=z(`d16ead82505dc285`);return p(),i(`div`,{style:`width: 0; height: 0`,tabindex:0,onFocus:t[0]||(t[0]=(...t)=>e.onFocus(...t)),onBlur:t[1]||(t[1]=(...t)=>e.onBlur(...t))},null,32)})()}}),Ye=t({name:`NBaseSelectGroupHeader`,props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0}},setup(){let{renderLabelRef:e,renderOptionRef:t,labelFieldRef:n,nodePropsRef:r}=u(ve);return{labelField:n,nodeProps:r,renderLabel:e,renderOption:t}},render(){let{clsPrefix:e,renderLabel:t,renderOption:n,nodeProps:r,tmNode:{rawNode:o}}=this,s=r==null?void 0:r(o),c=t?t(o,!1):Q(o[this.labelField],o,!1),l=(p(),i(`div`,a(s,{class:[`${e}-base-select-group-header`,s==null?void 0:s.class]}),[I(()=>c)],16));return o.render?o.render({node:l,option:o}):n?n({node:l,option:o,selected:!1}):l}}),Xe=t({name:`Checkmark`,render(){return(()=>{let e=z(`3c84eac8ae4e1f96`);return e[0]||(e[0]=r(`svg`,{xmlns:`http://www.w3.org/2000/svg`,viewBox:`0 0 16 16`},[r(`g`,{fill:`none`},[r(`path`,{d:`M14.046 3.486a.75.75 0 0 1-.032 1.06l-7.93 7.474a.85.85 0 0 1-1.188-.022l-2.68-2.72a.75.75 0 1 1 1.068-1.053l2.234 2.267l7.468-7.038a.75.75 0 0 1 1.06.032z`,fill:`currentColor`})])],-1))})()}}),Ze=[`onClick`,`onMouseenter`,`onMousemove`];function Qe(e,t){return p(),T(v,{name:`fade-in-scale-up-transition`},{default:()=>e?(p(),T(R,{key:1,clsPrefix:t,class:M(`${t}-base-select-option__check`)},{default:()=>l(Xe)},1032,[`clsPrefix`,`class`])):null},1024)}var $e=t({name:`NBaseSelectOption`,props:{clsPrefix:{type:String,required:!0},tmNode:{type:Object,required:!0}},setup(e){let{valueRef:t,pendingTmNodeRef:n,multipleRef:r,valueSetRef:i,renderLabelRef:a,renderOptionRef:o,labelFieldRef:s,valueFieldRef:c,showCheckmarkRef:l,nodePropsRef:d,handleOptionClick:f,handleOptionMouseEnter:p}=u(ve),m=Y(()=>{let{value:t}=n;return t?e.tmNode.key===t.key:!1});function h(t){let{tmNode:n}=e;n.disabled||f(t,n)}function g(t){let{tmNode:n}=e;n.disabled||p(t,n)}function _(t){let{tmNode:n}=e,{value:r}=m;n.disabled||r||p(t,n)}return{multiple:r,isGrouped:Y(()=>{let{tmNode:t}=e,{parent:n}=t;return n&&n.rawNode.type===`group`}),showCheckmark:l,nodeProps:d,isPending:m,isSelected:Y(()=>{let{value:n}=t,{value:a}=r;if(n===null)return!1;let o=e.tmNode.rawNode[c.value];if(a){let{value:e}=i;return e.has(o)}return n===o}),labelField:s,renderLabel:a,renderOption:o,handleMouseMove:_,handleMouseEnter:g,handleClick:h}},render(){let{clsPrefix:e,tmNode:{rawNode:t},isSelected:n,isPending:o,isGrouped:s,showCheckmark:c,nodeProps:l,renderOption:u,renderLabel:d,handleClick:f,handleMouseEnter:m,handleMouseMove:h}=this,g=Qe(n,e),_=d?[d(t,n),c&&g]:[Q(t[this.labelField],t,n),c&&g],v=l==null?void 0:l(t),y=(p(),i(`div`,a(v,{class:[`${e}-base-select-option`,t.class,v==null?void 0:v.class,{[`${e}-base-select-option--disabled`]:t.disabled,[`${e}-base-select-option--selected`]:n,[`${e}-base-select-option--grouped`]:s,[`${e}-base-select-option--pending`]:o,[`${e}-base-select-option--show-checkmark`]:c}],style:[(v==null?void 0:v.style)||``,t.style||``],onClick:Ee([f,v==null?void 0:v.onClick]),onMouseenter:Ee([m,v==null?void 0:v.onMouseenter]),onMousemove:Ee([h,v==null?void 0:v.onMousemove])}),[r(`div`,{class:M(`${e}-base-select-option__content`)},[I(()=>_)],2)],16,Ze));return t.render?t.render({node:y,option:t,selected:n}):u?u({node:y,option:t,selected:n}):y}}),et=A(`base-select-menu`,`
 line-height: 1.5;
 outline: none;
 z-index: 0;
 position: relative;
 border-radius: var(--n-border-radius);
 transition:
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 background-color: var(--n-color);
`,[A(`scrollbar`,`
 max-height: var(--n-height);
 `),A(`virtual-list`,`
 max-height: var(--n-height);
 `),A(`base-select-option`,`
 min-height: var(--n-option-height);
 font-size: var(--n-option-font-size);
 display: flex;
 align-items: center;
 `,[j(`content`,`
 z-index: 1;
 white-space: nowrap;
 text-overflow: ellipsis;
 overflow: hidden;
 `)]),A(`base-select-group-header`,`
 min-height: var(--n-option-height);
 font-size: .93em;
 display: flex;
 align-items: center;
 `),A(`base-select-menu-option-wrapper`,`
 position: relative;
 width: 100%;
 `),j(`loading, empty`,`
 display: flex;
 padding: 12px 32px;
 flex: 1;
 justify-content: center;
 `),j(`loading`,`
 color: var(--n-loading-color);
 font-size: var(--n-loading-size);
 `),j(`header`,`
 padding: 8px var(--n-option-padding-left);
 font-size: var(--n-option-font-size);
 transition: 
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 border-bottom: 1px solid var(--n-action-divider-color);
 color: var(--n-action-text-color);
 `),j(`action`,`
 padding: 8px var(--n-option-padding-left);
 font-size: var(--n-option-font-size);
 transition: 
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 border-top: 1px solid var(--n-action-divider-color);
 color: var(--n-action-text-color);
 `),A(`base-select-group-header`,`
 position: relative;
 cursor: default;
 padding: var(--n-option-padding);
 color: var(--n-group-header-text-color);
 `),A(`base-select-option`,`
 cursor: pointer;
 position: relative;
 padding: var(--n-option-padding);
 transition:
 color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 box-sizing: border-box;
 color: var(--n-option-text-color);
 opacity: 1;
 `,[k(`show-checkmark`,`
 padding-right: calc(var(--n-option-padding-right) + 20px);
 `),O(`&::before`,`
 content: "";
 position: absolute;
 left: 4px;
 right: 4px;
 top: 0;
 bottom: 0;
 border-radius: var(--n-border-radius);
 transition: background-color .3s var(--n-bezier);
 `),O(`&:active`,`
 color: var(--n-option-text-color-pressed);
 `),k(`grouped`,`
 padding-left: calc(var(--n-option-padding-left) * 1.5);
 `),k(`pending`,[O(`&::before`,`
 background-color: var(--n-option-color-pending);
 `)]),k(`selected`,`
 color: var(--n-option-text-color-active);
 `,[O(`&::before`,`
 background-color: var(--n-option-color-active);
 `),k(`pending`,[O(`&::before`,`
 background-color: var(--n-option-color-active-pending);
 `)])]),k(`disabled`,`
 cursor: not-allowed;
 `,[D(`selected`,`
 color: var(--n-option-text-color-disabled);
 `),k(`selected`,`
 opacity: var(--n-option-opacity-disabled);
 `)]),j(`check`,`
 font-size: 16px;
 position: absolute;
 right: calc(var(--n-option-padding-right) - 4px);
 top: calc(50% - 7px);
 color: var(--n-option-check-color);
 transition: color .3s var(--n-bezier);
 `,[De({enterScale:`0.5`})])])]);function tt(e){return Array.isArray(e)?e:[e]}var nt={STOP:`STOP`};function rt(e,t){let n=t(e);e.children!==void 0&&n!==nt.STOP&&e.children.forEach(e=>rt(e,t))}function it(e,t={}){let{preserveGroup:n=!1}=t,r=[],i=n?e=>{e.isLeaf||(r.push(e.key),a(e.children))}:e=>{e.isLeaf||(e.isGroup||r.push(e.key),a(e.children))};function a(e){e.forEach(i)}return a(e),r}function at(e,t){let{isLeaf:n}=e;return n===void 0?!t(e):n}function ot(e){return e.children}function st(e){return e.key}function ct(){return!1}function lt(e,t){let{isLeaf:n}=e;return!(n===!1&&!Array.isArray(t(e)))}function ut(e){return e.disabled===!0}function dt(e,t){return e.isLeaf===!1&&!Array.isArray(t(e))}function ft(e){var t;return e==null?[]:Array.isArray(e)?e:(t=e.checkedKeys)==null?[]:t}function pt(e){var t;return e==null||Array.isArray(e)||(t=e.indeterminateKeys)==null?[]:t}function mt(e,t){let n=new Set(e);return t.forEach(e=>{n.has(e)||n.add(e)}),Array.from(n)}function ht(e,t){let n=new Set(e);return t.forEach(e=>{n.has(e)&&n.delete(e)}),Array.from(n)}function gt(e){return(e==null?void 0:e.type)===`group`}function _t(e){let t=new Map;return e.forEach((e,n)=>{t.set(e.key,n)}),e=>{var n;return(n=t.get(e))==null?null:n}}var vt=class extends Error{constructor(){super(),this.message=`SubtreeNotLoadedError: checking a subtree whose required nodes are not fully loaded.`}};function yt(e,t,n,r){return Ct(t.concat(e),n,r,!1)}function bt(e,t){let n=new Set;return e.forEach(e=>{let r=t.treeNodeMap.get(e);if(r!==void 0){let e=r.parent;for(;e!==null&&!(e.disabled||n.has(e.key));)n.add(e.key),e=e.parent}}),n}function xt(e,t,n,r){let i=Ct(t,n,r,!1),a=Ct(e,n,r,!0),o=bt(e,n),s=[];return i.forEach(e=>{(a.has(e)||o.has(e))&&s.push(e)}),s.forEach(e=>i.delete(e)),i}function St(e,t){let{checkedKeys:n,keysToCheck:r,keysToUncheck:i,indeterminateKeys:a,cascade:o,leafOnly:s,checkStrategy:c,allowNotLoaded:l}=e;if(!o)return r===void 0?i===void 0?{checkedKeys:Array.from(n),indeterminateKeys:Array.from(a)}:{checkedKeys:ht(n,i),indeterminateKeys:Array.from(a)}:{checkedKeys:mt(n,r),indeterminateKeys:Array.from(a)};let{levelTreeNodeMap:u}=t,d;d=i===void 0?r===void 0?Ct(n,t,l,!1):yt(r,n,t,l):xt(i,n,t,l);let f=c===`parent`,p=c===`child`||s,m=d,h=new Set,g=Math.max.apply(null,Array.from(u.keys()));for(let e=g;e>=0;--e){let t=e===0,n=u.get(e);for(let e of n){if(e.isLeaf)continue;let{key:n,shallowLoaded:r}=e;if(p&&r&&e.children.forEach(e=>{!e.disabled&&!e.isLeaf&&e.shallowLoaded&&m.has(e.key)&&m.delete(e.key)}),e.disabled||!r)continue;let i=!0,a=!1,o=!0;for(let t of e.children){let e=t.key;if(!t.disabled){if(o&&(o=!1),m.has(e))a=!0;else if(h.has(e)){a=!0,i=!1;break}else if(i=!1,a)break}}i&&!o?(f&&e.children.forEach(e=>{!e.disabled&&m.has(e.key)&&m.delete(e.key)}),m.add(n)):a&&h.add(n),t&&p&&m.has(n)&&m.delete(n)}}return{checkedKeys:Array.from(m),indeterminateKeys:Array.from(h)}}function Ct(e,t,n,r){let{treeNodeMap:i,getChildren:a}=t,o=new Set,s=new Set(e);return e.forEach(e=>{let t=i.get(e);t!==void 0&&rt(t,e=>{if(e.disabled)return nt.STOP;let{key:t}=e;if(!o.has(t)&&(o.add(t),s.add(t),dt(e.rawNode,a))){if(r)return nt.STOP;if(!n)throw new vt}})}),s}function wt(e,{includeGroup:t=!1,includeSelf:n=!0},r){var i;let a=r.treeNodeMap,o=e==null||(i=a.get(e))==null?null:i,s={keyPath:[],treeNodePath:[],treeNode:o};if(o!=null&&o.ignored)return s.treeNode=null,s;for(;o;)!o.ignored&&(t||!o.isGroup)&&s.treeNodePath.push(o),o=o.parent;return s.treeNodePath.reverse(),n||s.treeNodePath.pop(),s.keyPath=s.treeNodePath.map(e=>e.key),s}function Tt(e){if(e.length===0)return null;let t=e[0];return t.isGroup||t.ignored||t.disabled?t.getNext():t}function Et(e,t){let n=e.siblings,r=n.length,{index:i}=e;return t?n[(i+1)%r]:i===n.length-1?null:n[i+1]}function Dt(e,t,{loop:n=!1,includeDisabled:r=!1}={}){let i=t===`prev`?Ot:Et,a={reverse:t===`prev`},o=!1,s=null;function c(t){if(t!==null){if(t===e){if(!o)o=!0;else if(!e.disabled&&!e.isGroup){s=e;return}}else if((!t.disabled||r)&&!t.ignored&&!t.isGroup){s=t;return}if(t.isGroup){let e=At(t,a);e===null?c(i(t,n)):s=e}else{let e=i(t,!1);if(e!==null)c(e);else{let e=kt(t);e!=null&&e.isGroup?c(i(e,n)):n&&c(i(t,!0))}}}}return c(e),s}function Ot(e,t){let n=e.siblings,r=n.length,{index:i}=e;return t?n[(i-1+r)%r]:i===0?null:n[i-1]}function kt(e){return e.parent}function At(e,t={}){let{reverse:n=!1}=t,{children:r}=e;if(r){let{length:e}=r,i=n?e-1:0,a=n?-1:e,o=n?-1:1;for(let e=i;e!==a;e+=o){let n=r[e];if(!n.disabled&&!n.ignored){if(n.isGroup){let e=At(n,t);if(e!==null)return e}else return n}}}return null}var jt={getChild(){return this.ignored?null:At(this)},getParent(){let{parent:e}=this;return e!=null&&e.isGroup?e.getParent():e},getNext(e={}){return Dt(this,`next`,e)},getPrev(e={}){return Dt(this,`prev`,e)}};function Mt(e,t){let n=t?new Set(t):void 0,r=[];function i(e){e.forEach(e=>{r.push(e),!(e.isLeaf||!e.children||e.ignored)&&(e.isGroup||n===void 0||n.has(e.key))&&i(e.children)})}return i(e),r}function Nt(e,t){let n=e.key;for(;t;){if(t.key===n)return!0;t=t.parent}return!1}function Pt(e,t,n,r,i,a=null,o=0){let s=[];return e.forEach((c,l)=>{var u;let d=Object.create(r);if(d.rawNode=c,d.siblings=s,d.level=o,d.index=l,d.isFirstChild=l===0,d.isLastChild=l+1===e.length,d.parent=a,!d.ignored){let e=i(c);Array.isArray(e)&&(d.children=Pt(e,t,n,r,i,d,o+1))}s.push(d),t.set(d.key,d),n.has(o)||n.set(o,[]),(u=n.get(o))==null||u.push(d)}),s}function Ft(e,t={}){var n;let r=new Map,i=new Map,{getDisabled:a=ut,getIgnored:o=ct,getIsGroup:s=gt,getKey:c=st}=t,l=(n=t.getChildren)==null?ot:n,u=t.ignoreEmptyChildren?e=>{let t=l(e);return Array.isArray(t)?t.length?t:null:t}:l,d=Pt(e,r,i,Object.assign({get key(){return c(this.rawNode)},get disabled(){return a(this.rawNode)},get isGroup(){return s(this.rawNode)},get isLeaf(){return at(this.rawNode,u)},get shallowLoaded(){return lt(this.rawNode,u)},get ignored(){return o(this.rawNode)},contains(e){return Nt(this,e)}},jt),u);function f(e){if(e==null)return null;let t=r.get(e);return t&&!t.isGroup&&!t.ignored?t:null}function p(e){if(e==null)return null;let t=r.get(e);return t&&!t.ignored?t:null}function m(e,t){let n=p(e);return n?n.getPrev(t):null}function h(e,t){let n=p(e);return n?n.getNext(t):null}function g(e){let t=p(e);return t?t.getParent():null}function _(e){let t=p(e);return t?t.getChild():null}let v={treeNodes:d,treeNodeMap:r,levelTreeNodeMap:i,maxLevel:Math.max(...i.keys()),getChildren:u,getFlattenedNodes(e){return Mt(d,e)},getNode:f,getPrev:m,getNext:h,getParent:g,getChild:_,getFirstAvailableNode(){return Tt(d)},getPath(e,t={}){return wt(e,t,v)},getCheckedKeys(e,t={}){let{cascade:n=!0,leafOnly:r=!1,checkStrategy:i=`all`,allowNotLoaded:a=!1}=t;return St({checkedKeys:ft(e),indeterminateKeys:pt(e),cascade:n,leafOnly:r,checkStrategy:i,allowNotLoaded:a},v)},check(e,t,n={}){let{cascade:r=!0,leafOnly:i=!1,checkStrategy:a=`all`,allowNotLoaded:o=!1}=n;return St({checkedKeys:ft(t),indeterminateKeys:pt(t),keysToCheck:e==null?[]:tt(e),cascade:r,leafOnly:i,checkStrategy:a,allowNotLoaded:o},v)},uncheck(e,t,n={}){let{cascade:r=!0,leafOnly:i=!1,checkStrategy:a=`all`,allowNotLoaded:o=!1}=n;return St({checkedKeys:ft(t),indeterminateKeys:pt(t),keysToUncheck:e==null?[]:tt(e),cascade:r,leafOnly:i,checkStrategy:a,allowNotLoaded:o},v)},getNonLeafKeys(e={}){return it(d,e)}};return v}var It=[`tabindex`,`onFocusin`,`onFocusout`,`onKeyup`,`onKeydown`,`onMousedown`,`onMouseenter`,`onMouseleave`],Lt=t({name:`InternalSelectMenu`,props:e(e({},L.props),{},{clsPrefix:{type:String,required:!0},scrollable:{type:Boolean,default:!0},treeMate:{type:Object,required:!0},multiple:Boolean,size:{type:String,default:`medium`},value:{type:[String,Number,Array],default:null},autoPending:Boolean,virtualScroll:{type:Boolean,default:!0},show:{type:Boolean,default:!0},labelField:{type:String,default:`label`},valueField:{type:String,default:`value`},loading:Boolean,focusable:Boolean,renderLabel:Function,renderOption:Function,nodeProps:Function,showCheckmark:{type:Boolean,default:!0},onMousedown:Function,onScroll:Function,onFocus:Function,onBlur:Function,onKeyup:Function,onKeydown:Function,onTabOut:Function,onMouseenter:Function,onMouseleave:Function,onResize:Function,resetMenuOnOptionsChange:{type:Boolean,default:!0},inlineThemeDisabled:Boolean,scrollbarProps:Object,onToggle:Function}),setup(t){let{mergedClsPrefixRef:n,mergedRtlRef:r,mergedComponentPropsRef:i}=te(t),a=re(`InternalSelectMenu`,r,n),s=L(`InternalSelectMenu`,`-internal-select-menu`,et,Oe,t,y(t,`clsPrefix`)),c=S(null),l=S(null),u=S(null),d=f(()=>t.treeMate.getFlattenedNodes()),p=f(()=>_t(d.value)),g=S(null);function v(){let{treeMate:e}=t,n=null,{value:r}=t;r===null?n=e.getFirstAvailableNode():(n=t.multiple?e.getNode((r||[])[(r||[]).length-1]):e.getNode(r),(!n||n.disabled)&&(n=e.getFirstAvailableNode())),H(n||null)}function b(){let{value:e}=g;e&&!t.treeMate.getNode(e.key)&&(g.value=null)}let x;_(()=>t.show,e=>{e?x=_(()=>t.treeMate,()=>{t.resetMenuOnOptionsChange?(t.autoPending?v():b(),o(U)):b()},{immediate:!0}):x==null||x()},{immediate:!0}),E(()=>{x==null||x()});let C=f(()=>oe(s.value.self[N(`optionHeight`,t.size)])),w=f(()=>q(s.value.self[N(`padding`,t.size)])),T=f(()=>t.multiple&&Array.isArray(t.value)?new Set(t.value):new Set),D=f(()=>{let e=d.value;return e&&e.length===0}),O=f(()=>{var e;return i==null||(e=i.value)==null||(e=e.Select)==null?void 0:e.renderEmpty});function k(e){let{onToggle:n}=t;n&&n(e)}function A(e){let{onScroll:n}=t;n&&n(e)}function j(e){var t;(t=u.value)==null||t.sync(),A(e)}function M(){var e;(e=u.value)==null||e.sync()}function P(){let{value:e}=g;return e||null}function F(e,t){t.disabled||H(t,!1)}function I(e,t){t.disabled||k(t)}function R(e){var n;Me(e,`action`)||(n=t.onKeyup)==null||n.call(t,e)}function z(e){var n;Me(e,`action`)||(n=t.onKeydown)==null||n.call(t,e)}function B(e){var n;(n=t.onMousedown)==null||n.call(t,e),!t.focusable&&e.preventDefault()}function V(){let{value:e}=g;e&&H(e.getNext({loop:!0}),!0)}function ne(){let{value:e}=g;e&&H(e.getPrev({loop:!0}),!0)}function H(e,t=!1){g.value=e,t&&U()}function U(){var e,n;let r=g.value;if(!r)return;let i=p.value(r.key);i!==null&&(t.virtualScroll?(e=l.value)==null||e.scrollTo({index:i}):(n=u.value)==null||n.scrollTo({index:i,elSize:C.value}))}function ie(e){var n,r;(n=c.value)!=null&&n.contains(e.target)&&((r=t.onFocus)==null||r.call(t,e))}function W(e){var n,r;(n=c.value)!=null&&n.contains(e.relatedTarget)||(r=t.onBlur)==null||r.call(t,e)}h(ve,{handleOptionMouseEnter:F,handleOptionClick:I,valueSetRef:T,pendingTmNodeRef:g,nodePropsRef:y(t,`nodeProps`),showCheckmarkRef:y(t,`showCheckmark`),multipleRef:y(t,`multiple`),valueRef:y(t,`value`),renderLabelRef:y(t,`renderLabel`),renderOptionRef:y(t,`renderOption`),labelFieldRef:y(t,`labelField`),valueFieldRef:y(t,`valueField`)}),h(me,c),m(()=>{let{value:e}=u;e&&e.sync()});let G=f(()=>{let{size:e}=t,{common:{cubicBezierEaseInOut:n},self:{height:r,borderRadius:i,color:a,groupHeaderTextColor:o,actionDividerColor:c,optionTextColorPressed:l,optionTextColor:u,optionTextColorDisabled:d,optionTextColorActive:f,optionOpacityDisabled:p,optionCheckColor:m,actionTextColor:h,optionColorPending:g,optionColorActive:_,loadingColor:v,loadingSize:y,optionColorActivePending:b,[N(`optionFontSize`,e)]:x,[N(`optionHeight`,e)]:S,[N(`optionPadding`,e)]:C}}=s.value;return{"--n-height":r,"--n-action-divider-color":c,"--n-action-text-color":h,"--n-bezier":n,"--n-border-radius":i,"--n-color":a,"--n-option-font-size":x,"--n-group-header-text-color":o,"--n-option-check-color":m,"--n-option-color-pending":g,"--n-option-color-active":_,"--n-option-color-active-pending":b,"--n-option-height":S,"--n-option-opacity-disabled":p,"--n-option-text-color":u,"--n-option-text-color-active":f,"--n-option-text-color-disabled":d,"--n-option-text-color-pressed":l,"--n-option-padding":C,"--n-option-padding-left":q(C,`left`),"--n-option-padding-right":q(C,`right`),"--n-loading-color":v,"--n-loading-size":y}}),{inlineThemeDisabled:K}=t,ae=K?ee(`internal-select-menu`,f(()=>t.size[0]),G,t):void 0,se={selfRef:c,next:V,prev:ne,getPendingTmNode:P};return qe(c,t.onResize),e({mergedTheme:s,mergedClsPrefix:n,rtlEnabled:a,virtualListRef:l,scrollbarRef:u,itemSize:C,padding:w,flattenedNodes:d,empty:D,mergedRenderEmpty:O,virtualListContainer(){let{value:e}=l;return e==null?void 0:e.listElRef},virtualListContent(){let{value:e}=l;return e==null?void 0:e.itemsElRef},doScroll:A,handleFocusin:ie,handleFocusout:W,handleKeyUp:R,handleKeyDown:z,handleMouseDown:B,handleVirtualListResize:M,handleVirtualListScroll:j,cssVars:K?void 0:G,themeClass:ae==null?void 0:ae.themeClass,onRender:ae==null?void 0:ae.onRender},se)},render(){let{$slots:e,virtualScroll:t,clsPrefix:n,mergedTheme:r,themeClass:o,onRender:s}=this;return s==null||s(),p(),i(`div`,{ref:`selfRef`,tabindex:this.focusable?0:-1,class:M([`${n}-base-select-menu`,`${n}-base-select-menu--${this.size}-size`,this.rtlEnabled&&`${n}-base-select-menu--rtl`,o,this.multiple&&`${n}-base-select-menu--multiple`]),style:C(this.cssVars),onFocusin:this.handleFocusin,onFocusout:this.handleFocusout,onKeyup:this.handleKeyUp,onKeydown:this.handleKeyDown,onMousedown:this.handleMouseDown,onMouseenter:this.onMouseenter,onMouseleave:this.onMouseleave},[I(()=>U(e.header,e=>e&&(p(),i(`div`,{class:M(`${n}-base-select-menu__header`),"data-header":!0,key:`header`},[I(()=>e)],2)))),this.loading?(p(),i(`div`,{key:0,class:M(`${n}-base-select-menu__loading`)},[(p(),T(ce,{clsPrefix:n,strokeWidth:20},null,8,[`clsPrefix`]))],2)):(p(),i(w,{key:1},[this.empty?(p(),i(`div`,{key:1,class:M(`${n}-base-select-menu__empty`),"data-empty":!0},[I(()=>V(e.empty,()=>{var e;return[((e=this.mergedRenderEmpty)==null?void 0:e.call(this))||(p(),T(xe,{theme:r.peers.Empty,themeOverrides:r.peerOverrides.Empty,size:this.size},null,8,[`theme`,`themeOverrides`,`size`]))]}))],2)):(p(),T(ie,a({key:0,ref:`scrollbarRef`,theme:r.peers.Scrollbar,themeOverrides:r.peerOverrides.Scrollbar,scrollable:this.scrollable,container:t?this.virtualListContainer:void 0,content:t?this.virtualListContent:void 0,onScroll:t?void 0:this.doScroll},this.scrollbarProps),{default:()=>t?(p(),T(Ue,{key:1,ref:`virtualListRef`,class:M(`${n}-virtual-list`),items:this.flattenedNodes,itemSize:this.itemSize,showScrollbar:!1,paddingTop:this.padding.top,paddingBottom:this.padding.bottom,onResize:this.handleVirtualListResize,onScroll:this.handleVirtualListScroll,itemResizable:!0},{default:({item:e})=>e.isGroup?(p(),T(Ye,{key:e.key,clsPrefix:n,tmNode:e},null,8,[`clsPrefix`,`tmNode`])):e.ignored?null:(p(),T($e,{clsPrefix:n,key:e.key,tmNode:e},null,8,[`clsPrefix`,`tmNode`]))},1032,[`class`,`items`,`itemSize`,`paddingTop`,`paddingBottom`,`onResize`,`onScroll`])):(p(),i(`div`,{key:4,class:M(`${n}-base-select-menu-option-wrapper`),style:C({paddingTop:this.padding.top,paddingBottom:this.padding.bottom})},[I(()=>this.flattenedNodes.map(e=>e.isGroup?(p(),T(Ye,{key:e.key,clsPrefix:n,tmNode:e},null,8,[`clsPrefix`,`tmNode`])):(p(),T($e,{clsPrefix:n,key:e.key,tmNode:e},null,8,[`clsPrefix`,`tmNode`]))))],6))},1040,[`theme`,`themeOverrides`,`scrollable`,`container`,`content`,`onScroll`]))],64)),I(()=>U(e.action,e=>e&&[(p(),i(`div`,{class:M(`${n}-base-select-menu__action`),"data-action":!0,key:`action`},[I(()=>e)],2)),(p(),T(Je,{onFocus:this.onTabOut,key:`focus-detector`},null,8,[`onFocus`]))]))],46,It)}});function Rt(e){return e.type===`group`}function zt(e){return e.type===`ignored`}function Bt(e,t){try{return!!(1+t.toString().toLowerCase().indexOf(e.trim().toLowerCase()))}catch(e){return!1}}function Vt(e,t){return{getIsGroup:Rt,getIgnored:zt,getKey(t){return Rt(t)?t.name||t.key||`key-required`:t[e]},getChildren(e){return e[t]}}}function Ht(e,t,n,r){if(!t)return e;function i(e){if(!Array.isArray(e))return[];let a=[];for(let o of e)if(Rt(o)){let e=i(o[r]);e.length&&a.push(Object.assign({},o,{[r]:e}))}else if(zt(o))continue;else t(n,o)&&a.push(o);return a}return i(e)}function Ut(e,t,n){let r=new Map;return e.forEach(e=>{Rt(e)?e[n].forEach(e=>{r.set(e[t],e)}):r.set(e[t],e)}),r}var Wt=O([A(`base-selection`,`
 --n-padding-single: var(--n-padding-single-top) var(--n-padding-single-right) var(--n-padding-single-bottom) var(--n-padding-single-left);
 --n-padding-multiple: var(--n-padding-multiple-top) var(--n-padding-multiple-right) var(--n-padding-multiple-bottom) var(--n-padding-multiple-left);
 position: relative;
 z-index: auto;
 box-shadow: none;
 width: 100%;
 max-width: 100%;
 display: inline-block;
 vertical-align: bottom;
 border-radius: var(--n-border-radius);
 min-height: var(--n-height);
 line-height: 1.5;
 font-size: var(--n-font-size);
 `,[A(`base-loading`,`
 color: var(--n-loading-color);
 `),A(`base-selection-tags`,`min-height: var(--n-height);`),j(`border, state-border`,`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 pointer-events: none;
 border: var(--n-border);
 border-radius: inherit;
 transition:
 box-shadow .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `),j(`state-border`,`
 z-index: 1;
 border-color: #0000;
 `),A(`base-suffix`,`
 cursor: pointer;
 position: absolute;
 top: 50%;
 transform: translateY(-50%);
 right: 10px;
 `,[j(`arrow`,`
 font-size: var(--n-arrow-size);
 color: var(--n-arrow-color);
 transition: color .3s var(--n-bezier);
 `)]),A(`base-selection-overlay`,`
 display: flex;
 align-items: center;
 white-space: nowrap;
 pointer-events: none;
 position: absolute;
 top: 0;
 right: 0;
 bottom: 0;
 left: 0;
 padding: var(--n-padding-single);
 transition: color .3s var(--n-bezier);
 `,[j(`wrapper`,`
 flex-basis: 0;
 flex-grow: 1;
 overflow: hidden;
 text-overflow: ellipsis;
 `)]),A(`base-selection-placeholder`,`
 color: var(--n-placeholder-color);
 `,[j(`inner`,`
 max-width: 100%;
 overflow: hidden;
 `)]),A(`base-selection-tags`,`
 cursor: pointer;
 outline: none;
 box-sizing: border-box;
 position: relative;
 z-index: auto;
 display: flex;
 padding: var(--n-padding-multiple);
 flex-wrap: wrap;
 align-items: center;
 width: 100%;
 vertical-align: bottom;
 background-color: var(--n-color);
 border-radius: inherit;
 transition:
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 `),A(`base-selection-label`,`
 height: var(--n-height);
 display: inline-flex;
 width: 100%;
 vertical-align: bottom;
 cursor: pointer;
 outline: none;
 z-index: auto;
 box-sizing: border-box;
 position: relative;
 transition:
 color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 border-radius: inherit;
 background-color: var(--n-color);
 align-items: center;
 `,[A(`base-selection-input`,`
 font-size: inherit;
 line-height: inherit;
 outline: none;
 cursor: pointer;
 box-sizing: border-box;
 border:none;
 width: 100%;
 padding: var(--n-padding-single);
 background-color: #0000;
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 caret-color: var(--n-caret-color);
 `,[j(`content`,`
 text-overflow: ellipsis;
 overflow: hidden;
 white-space: nowrap; 
 `)]),j(`render-label`,`
 color: var(--n-text-color);
 `)]),D(`disabled`,[O(`&:hover`,[j(`state-border`,`
 box-shadow: var(--n-box-shadow-hover);
 border: var(--n-border-hover);
 `)]),k(`focus`,[j(`state-border`,`
 box-shadow: var(--n-box-shadow-focus);
 border: var(--n-border-focus);
 `)]),k(`active`,[j(`state-border`,`
 box-shadow: var(--n-box-shadow-active);
 border: var(--n-border-active);
 `),A(`base-selection-label`,`background-color: var(--n-color-active);`),A(`base-selection-tags`,`background-color: var(--n-color-active);`)])]),k(`disabled`,`cursor: not-allowed;`,[j(`arrow`,`
 color: var(--n-arrow-color-disabled);
 `),A(`base-selection-label`,`
 cursor: not-allowed;
 background-color: var(--n-color-disabled);
 `,[A(`base-selection-input`,`
 cursor: not-allowed;
 color: var(--n-text-color-disabled);
 `),j(`render-label`,`
 color: var(--n-text-color-disabled);
 `)]),A(`base-selection-tags`,`
 cursor: not-allowed;
 background-color: var(--n-color-disabled);
 `),A(`base-selection-placeholder`,`
 cursor: not-allowed;
 color: var(--n-placeholder-color-disabled);
 `)]),A(`base-selection-input-tag`,`
 height: calc(var(--n-height) - 6px);
 line-height: calc(var(--n-height) - 6px);
 outline: none;
 display: none;
 position: relative;
 margin-bottom: 3px;
 max-width: 100%;
 vertical-align: bottom;
 `,[j(`input`,`
 font-size: inherit;
 font-family: inherit;
 min-width: 1px;
 padding: 0;
 background-color: #0000;
 outline: none;
 border: none;
 max-width: 100%;
 overflow: hidden;
 width: 1em;
 line-height: inherit;
 cursor: pointer;
 color: var(--n-text-color);
 caret-color: var(--n-caret-color);
 `),j(`mirror`,`
 position: absolute;
 left: 0;
 top: 0;
 white-space: pre;
 visibility: hidden;
 user-select: none;
 -webkit-user-select: none;
 opacity: 0;
 `)]),[`warning`,`error`].map(e=>k(`${e}-status`,[j(`state-border`,`border: var(--n-border-${e});`),D(`disabled`,[O(`&:hover`,[j(`state-border`,`
 box-shadow: var(--n-box-shadow-hover-${e});
 border: var(--n-border-hover-${e});
 `)]),k(`active`,[j(`state-border`,`
 box-shadow: var(--n-box-shadow-active-${e});
 border: var(--n-border-active-${e});
 `),A(`base-selection-label`,`background-color: var(--n-color-active-${e});`),A(`base-selection-tags`,`background-color: var(--n-color-active-${e});`)]),k(`focus`,[j(`state-border`,`
 box-shadow: var(--n-box-shadow-focus-${e});
 border: var(--n-border-focus-${e});
 `)])])]))]),A(`base-selection-popover`,`
 margin-bottom: -3px;
 display: flex;
 flex-wrap: wrap;
 margin-right: -8px;
 `),A(`base-selection-tag-wrapper`,`
 max-width: 100%;
 display: inline-flex;
 padding: 0 7px 3px 0;
 `,[O(`&:last-child`,`padding-right: 0;`),A(`tag`,`
 font-size: 14px;
 max-width: 100%;
 `,[j(`content`,`
 line-height: 1.25;
 text-overflow: ellipsis;
 overflow: hidden;
 `)])])]),Gt=[`disabled`,`value`,`autofocus`,`onBlur`,`onFocus`,`onKeydown`,`onInput`,`onCompositionstart`,`onCompositionend`],Kt=[`tabindex`],qt=[`title`],Jt=[`value`,`readonly`,`disabled`,`autofocus`,`onFocus`,`onBlur`,`onInput`,`onCompositionstart`,`onCompositionend`],Yt=[`tabindex`],Xt=[`onClick`,`onMouseenter`,`onMouseleave`,`onKeydown`,`onFocusin`,`onFocusout`,`onMousedown`],Zt=t({name:`InternalSelection`,props:e(e({},L.props),{},{clsPrefix:{type:String,required:!0},bordered:{type:Boolean,default:void 0},active:Boolean,pattern:{type:String,default:``},placeholder:String,selectedOption:{type:Object,default:null},selectedOptions:{type:Array,default:null},labelField:{type:String,default:`label`},valueField:{type:String,default:`value`},multiple:Boolean,filterable:Boolean,clearable:Boolean,disabled:Boolean,size:{type:String,default:`medium`},loading:Boolean,autofocus:Boolean,showArrow:{type:Boolean,default:!0},inputProps:Object,focused:Boolean,renderTag:Function,onKeydown:Function,onClick:Function,onBlur:Function,onFocus:Function,onDeleteOption:Function,maxTagCount:[String,Number],ellipsisTagPopoverProps:Object,onClear:Function,onPatternInput:Function,onPatternFocus:Function,onPatternBlur:Function,renderLabel:Function,status:String,inlineThemeDisabled:Boolean,ignoreComposition:{type:Boolean,default:!0},onResize:Function}),setup(e){let{mergedClsPrefixRef:t,mergedRtlRef:n}=te(e),r=re(`InternalSelection`,n,t),i=S(null),a=S(null),s=S(null),c=S(null),l=S(null),u=S(null),d=S(null),p=S(null),h=S(null),v=S(null),b=S(!1),x=S(!1),C=S(!1),w=L(`InternalSelection`,`-internal-selection`,Wt,Te,e,y(e,`clsPrefix`)),T=f(()=>e.clearable&&!e.disabled&&(C.value||e.active)),E=f(()=>e.selectedOption?e.renderTag?e.renderTag({option:e.selectedOption,handleClose:()=>{}}):e.renderLabel?e.renderLabel(e.selectedOption,!0):Q(e.selectedOption[e.labelField],e.selectedOption,!0):e.placeholder),D=f(()=>{let t=e.selectedOption;if(t)return t[e.labelField]}),O=f(()=>e.multiple?!!(Array.isArray(e.selectedOptions)&&e.selectedOptions.length):e.selectedOption!==null);function k(){let{value:t}=i;if(t){let{value:r}=a;if(r){var n;r.style.width=`${t.offsetWidth}px`,e.maxTagCount!==`responsive`&&((n=h.value)==null||n.sync({showAllItemsBeforeCalculate:!1}))}}}function A(){let{value:e}=v;e&&(e.style.display=`none`)}function j(){let{value:e}=v;e&&(e.style.display=`inline-block`)}_(y(e,`active`),e=>{e||A()}),_(y(e,`pattern`),()=>{e.multiple&&o(k)});function M(t){let{onFocus:n}=e;n&&n(t)}function P(t){let{onBlur:n}=e;n&&n(t)}function F(t){let{onDeleteOption:n}=e;n&&n(t)}function I(t){let{onClear:n}=e;n&&n(t)}function R(t){let{onPatternInput:n}=e;n&&n(t)}function z(e){var t;(!e.relatedTarget||!((t=s.value)!=null&&t.contains(e.relatedTarget)))&&M(e)}function B(e){var t;(t=s.value)!=null&&t.contains(e.relatedTarget)||P(e)}function V(e){I(e)}function ne(){C.value=!0}function H(){C.value=!1}function U(t){!e.active||!e.filterable||t.target!==a.value&&t.preventDefault()}function ie(e){F(e)}let W=S(!1);function G(t){if(t.key===`Backspace`&&!W.value&&!e.pattern.length){let{selectedOptions:t}=e;t!=null&&t.length&&ie(t[t.length-1])}}let K=null;function ae(t){let{value:n}=i;n&&(n.textContent=t.target.value,k()),e.ignoreComposition&&W.value?K=t:R(t)}function oe(){W.value=!0}function se(){W.value=!1,e.ignoreComposition&&R(K),K=null}function ce(t){var n;x.value=!0,(n=e.onPatternFocus)==null||n.call(e,t)}function le(t){var n;x.value=!1,(n=e.onPatternBlur)==null||n.call(e,t)}function J(){if(e.filterable){var t,n;x.value=!1,(t=u.value)==null||t.blur(),(n=a.value)==null||n.blur()}else if(e.multiple){let{value:e}=c;e==null||e.blur()}else{let{value:e}=l;e==null||e.blur()}}function Y(){var t,n;if(e.filterable){var r;x.value=!1,(r=u.value)==null||r.focus()}else e.multiple?(t=c.value)==null||t.focus():(n=l.value)==null||n.focus()}function X(){let{value:e}=a;e&&(j(),e.focus())}function ue(){let{value:e}=a;e&&e.blur()}function de(e){let{value:t}=d;t&&t.setTextContent(`+${e}`)}function fe(){let{value:e}=p;return e}function pe(){return a.value}let me=null;function he(){me!==null&&window.clearTimeout(me)}function ge(){e.active||(he(),me=window.setTimeout(()=>{O.value&&(b.value=!0)},100))}function _e(){he()}function ve(e){e||(he(),b.value=!1)}_(O,e=>{e||(b.value=!1)}),m(()=>{g(()=>{let t=u.value;t&&(e.disabled?t.removeAttribute(`tabindex`):t.tabIndex=x.value?-1:0)})}),qe(s,e.onResize);let{inlineThemeDisabled:ye}=e,be=f(()=>{let{size:t}=e,{common:{cubicBezierEaseInOut:n},self:{fontWeight:r,borderRadius:i,color:a,placeholderColor:o,textColor:s,paddingSingle:c,paddingMultiple:l,caretColor:u,colorDisabled:d,textColorDisabled:f,placeholderColorDisabled:p,colorActive:m,boxShadowFocus:h,boxShadowActive:g,boxShadowHover:_,border:v,borderFocus:y,borderHover:b,borderActive:x,arrowColor:S,arrowColorDisabled:C,loadingColor:T,colorActiveWarning:E,boxShadowFocusWarning:D,boxShadowActiveWarning:O,boxShadowHoverWarning:k,borderWarning:A,borderFocusWarning:j,borderHoverWarning:M,borderActiveWarning:P,colorActiveError:F,boxShadowFocusError:ee,boxShadowActiveError:I,boxShadowHoverError:L,borderError:R,borderFocusError:z,borderHoverError:te,borderActiveError:B,clearColor:V,clearColorHover:ne,clearColorPressed:H,clearSize:re,arrowSize:U,[N(`height`,t)]:ie,[N(`fontSize`,t)]:W}}=w.value,G=q(c),K=q(l);return{"--n-bezier":n,"--n-border":v,"--n-border-active":x,"--n-border-focus":y,"--n-border-hover":b,"--n-border-radius":i,"--n-box-shadow-active":g,"--n-box-shadow-focus":h,"--n-box-shadow-hover":_,"--n-caret-color":u,"--n-color":a,"--n-color-active":m,"--n-color-disabled":d,"--n-font-size":W,"--n-height":ie,"--n-padding-single-top":G.top,"--n-padding-multiple-top":K.top,"--n-padding-single-right":G.right,"--n-padding-multiple-right":K.right,"--n-padding-single-left":G.left,"--n-padding-multiple-left":K.left,"--n-padding-single-bottom":G.bottom,"--n-padding-multiple-bottom":K.bottom,"--n-placeholder-color":o,"--n-placeholder-color-disabled":p,"--n-text-color":s,"--n-text-color-disabled":f,"--n-arrow-color":S,"--n-arrow-color-disabled":C,"--n-loading-color":T,"--n-color-active-warning":E,"--n-box-shadow-focus-warning":D,"--n-box-shadow-active-warning":O,"--n-box-shadow-hover-warning":k,"--n-border-warning":A,"--n-border-focus-warning":j,"--n-border-hover-warning":M,"--n-border-active-warning":P,"--n-color-active-error":F,"--n-box-shadow-focus-error":ee,"--n-box-shadow-active-error":I,"--n-box-shadow-hover-error":L,"--n-border-error":R,"--n-border-focus-error":z,"--n-border-hover-error":te,"--n-border-active-error":B,"--n-clear-size":re,"--n-clear-color":V,"--n-clear-color-hover":ne,"--n-clear-color-pressed":H,"--n-arrow-size":U,"--n-font-weight":r}}),Z=ye?ee(`internal-selection`,f(()=>e.size[0]),be,e):void 0;return{mergedTheme:w,mergedClearable:T,mergedClsPrefix:t,rtlEnabled:r,patternInputFocused:x,filterablePlaceholder:E,label:D,selected:O,showTagsPanel:b,isComposing:W,counterRef:d,counterWrapperRef:p,patternInputMirrorRef:i,patternInputRef:a,selfRef:s,multipleElRef:c,singleElRef:l,patternInputWrapperRef:u,overflowRef:h,inputTagElRef:v,handleMouseDown:U,handleFocusin:z,handleClear:V,handleMouseEnter:ne,handleMouseLeave:H,handleDeleteOption:ie,handlePatternKeyDown:G,handlePatternInputInput:ae,handlePatternInputBlur:le,handlePatternInputFocus:ce,handleMouseEnterCounter:ge,handleMouseLeaveCounter:_e,handleFocusout:B,handleCompositionEnd:se,handleCompositionStart:oe,onPopoverUpdateShow:ve,focus:Y,focusInput:X,blur:J,blurInput:ue,updateCounter:de,getCounter:fe,getTail:pe,renderLabel:e.renderLabel,cssVars:ye?void 0:be,themeClass:Z==null?void 0:Z.themeClass,onRender:Z==null?void 0:Z.onRender}},render(){let{status:t,multiple:n,size:o,disabled:s,filterable:c,maxTagCount:l,bordered:u,clsPrefix:d,ellipsisTagPopoverProps:f,onRender:m,renderTag:h,renderLabel:g}=this;m==null||m();let _=l===`responsive`,v=typeof l==`number`,y=_||v,b=(p(),T(H,null,{default:()=>(p(),T(we,{clsPrefix:d,loading:this.loading,showArrow:this.showArrow,showClear:this.mergedClearable&&this.selected,onClear:this.handleClear},{default:()=>{var e,t;return(e=(t=this.$slots).arrow)==null?void 0:e.call(t)}},1032,[`clsPrefix`,`loading`,`showArrow`,`showClear`,`onClear`]))},1024)),x;if(n){let{labelField:t}=this,n=e=>(p(),i(`div`,{class:M(`${d}-base-selection-tag-wrapper`),key:e.value},[h?(p(),i(w,{key:0},[I(()=>h({option:e,handleClose:()=>{this.handleDeleteOption(e)}}))],64)):(p(),T(Ce,{key:1,size:o,closable:!e.disabled,disabled:s,onClose:()=>{this.handleDeleteOption(e)},internalCloseIsButtonTag:!1,internalCloseFocusable:!1},{default:()=>g?g(e,!0):Q(e[t],e,!0)},1032,[`size`,`closable`,`disabled`,`onClose`]))],2)),u=()=>(v?this.selectedOptions.slice(0,l):this.selectedOptions).map(n),m=c?(p(),i(`div`,{class:M(`${d}-base-selection-input-tag`),ref:`inputTagElRef`,key:`__input-tag__`},[r(`input`,a(this.inputProps,{ref:`patternInputRef`,tabindex:-1,disabled:s,value:this.pattern,autofocus:this.autofocus,class:`${d}-base-selection-input-tag__input`,onBlur:this.handlePatternInputBlur,onFocus:this.handlePatternInputFocus,onKeydown:this.handlePatternKeyDown,onInput:this.handlePatternInputInput,onCompositionstart:this.handleCompositionStart,onCompositionend:this.handleCompositionEnd}),null,16,Gt),r(`span`,{ref:`patternInputMirrorRef`,class:M(`${d}-base-selection-input-tag__mirror`)},[I(()=>this.pattern)],2)],2)):null,S=_?()=>(p(),i(`div`,{class:M(`${d}-base-selection-tag-wrapper`),ref:`counterWrapperRef`},[(p(),T(Ce,{size:o,ref:`counterRef`,onMouseenter:this.handleMouseEnterCounter,onMouseleave:this.handleMouseLeaveCounter,disabled:s},null,8,[`size`,`onMouseenter`,`onMouseleave`,`disabled`]))],2)):void 0,C;if(v){let e=this.selectedOptions.length-l;e>0&&(C=(t=>(p(),i(`div`,{class:M(`${d}-base-selection-tag-wrapper`),key:`__counter__`},[(p(),T(Ce,{size:o,ref:`counterRef`,onMouseenter:this.handleMouseEnterCounter,disabled:s},{default:()=>`+${e}`},1032,[`size`,`onMouseenter`,`disabled`]))],2)))(C))}let E=_?c?(p(),T(Ge,{key:3,ref:`overflowRef`,updateCounter:this.updateCounter,getCounter:this.getCounter,getTail:this.getTail,style:{width:`100%`,display:`flex`,overflow:`hidden`}},{default:u,counter:S,tail:()=>m},1032,[`updateCounter`,`getCounter`,`getTail`])):(p(),T(Ge,{key:4,ref:`overflowRef`,updateCounter:this.updateCounter,getCounter:this.getCounter,style:{width:`100%`,display:`flex`,overflow:`hidden`}},{default:u,counter:S},1032,[`updateCounter`,`getCounter`])):v&&C?u().concat(C):u(),D=y?()=>(p(),i(`div`,{class:M(`${d}-base-selection-popover`)},[_?(p(),i(w,{key:0},[I(()=>u())],64)):(p(),i(w,{key:1},[I(()=>this.selectedOptions.map(n))],64))],2)):void 0,O=y?e({show:this.showTagsPanel,trigger:`hover`,overlap:!0,placement:`top`,width:`trigger`,onUpdateShow:this.onPopoverUpdateShow,theme:this.mergedTheme.peers.Popover,themeOverrides:this.mergedTheme.peerOverrides.Popover},f):null,k=!this.selected&&(!this.active||!this.pattern&&!this.isComposing)?(p(),i(`div`,{key:5,class:M(`${d}-base-selection-placeholder ${d}-base-selection-overlay`)},[r(`div`,{class:M(`${d}-base-selection-placeholder__inner`)},[I(()=>this.placeholder)],2)],2)):null,A=c?(p(),i(`div`,{key:6,ref:`patternInputWrapperRef`,class:M(`${d}-base-selection-tags`)},[I(()=>E),_?I(()=>null):(p(),i(w,{key:1},[I(()=>m)],64)),I(()=>b)],2)):(p(),i(`div`,{key:7,ref:`multipleElRef`,class:M(`${d}-base-selection-tags`),tabindex:s?void 0:0},[I(()=>E),I(()=>b)],10,Kt));x=(e=>(p(),i(w,{key:8},[y?(p(),T(be,a({key:0},O,{scrollable:!0,style:`max-height: calc(var(--v-target-height) * 6.6);`}),{trigger:()=>A,default:D},1040)):(p(),i(w,{key:1},[I(()=>A)],64)),I(()=>k)],64)))(x)}else if(c){let e=this.pattern||this.isComposing,t=this.active?!e:!this.selected,n=!this.active&&this.selected;x=(e=>(p(),i(`div`,{key:9,ref:`patternInputWrapperRef`,class:M(`${d}-base-selection-label`),title:this.patternInputFocused?void 0:Ke(this.label)},[r(`input`,a(this.inputProps,{ref:`patternInputRef`,class:`${d}-base-selection-input`,value:this.active?this.pattern:``,placeholder:``,readonly:s,disabled:s,tabindex:-1,autofocus:this.autofocus,onFocus:this.handlePatternInputFocus,onBlur:this.handlePatternInputBlur,onInput:this.handlePatternInputInput,onCompositionstart:this.handleCompositionStart,onCompositionend:this.handleCompositionEnd}),null,16,Jt),n?(p(),i(`div`,{class:M(`${d}-base-selection-label__render-label ${d}-base-selection-overlay`),key:`input`},[r(`div`,{class:M(`${d}-base-selection-overlay__wrapper`)},[h?(p(),i(w,{key:0},[I(()=>h({option:this.selectedOption,handleClose:()=>{}}))],64)):(p(),i(w,{key:1},[g?(p(),i(w,{key:0},[I(()=>g(this.selectedOption,!0))],64)):(p(),i(w,{key:1},[I(()=>Q(this.label,this.selectedOption,!0))],64))],64))],2)],2)):I(()=>null),t?(p(),i(`div`,{class:M(`${d}-base-selection-placeholder ${d}-base-selection-overlay`),key:`placeholder`},[r(`div`,{class:M(`${d}-base-selection-overlay__wrapper`)},[I(()=>this.filterablePlaceholder)],2)],2)):I(()=>null),I(()=>b)],10,qt)))(x)}else x=(e=>(p(),i(`div`,{key:10,ref:`singleElRef`,class:M(`${d}-base-selection-label`),tabindex:this.disabled?void 0:0},[this.label===void 0?(p(),i(`div`,{class:M(`${d}-base-selection-placeholder ${d}-base-selection-overlay`),key:`placeholder`},[r(`div`,{class:M(`${d}-base-selection-placeholder__inner`)},[I(()=>this.placeholder)],2)],2)):(p(),i(`div`,{class:M(`${d}-base-selection-input`),title:Ke(this.label),key:`input`},[r(`div`,{class:M(`${d}-base-selection-input__content`)},[h?(p(),i(w,{key:0},[I(()=>h({option:this.selectedOption,handleClose:()=>{}}))],64)):(p(),i(w,{key:1},[g?(p(),i(w,{key:0},[I(()=>g(this.selectedOption,!0))],64)):(p(),i(w,{key:1},[I(()=>Q(this.label,this.selectedOption,!0))],64))],64))],2)],10,[`title`])),I(()=>b)],10,Yt)))(x);return p(),i(`div`,{ref:`selfRef`,class:M([`${d}-base-selection`,this.rtlEnabled&&`${d}-base-selection--rtl`,this.themeClass,t&&`${d}-base-selection--${t}-status`,{[`${d}-base-selection--active`]:this.active,[`${d}-base-selection--selected`]:this.selected||this.active&&this.pattern,[`${d}-base-selection--disabled`]:this.disabled,[`${d}-base-selection--multiple`]:this.multiple,[`${d}-base-selection--focus`]:this.focused}]),style:C(this.cssVars),onClick:this.onClick,onMouseenter:this.handleMouseEnter,onMouseleave:this.handleMouseLeave,onKeydown:this.onKeydown,onFocusin:this.handleFocusin,onFocusout:this.handleFocusout,onMousedown:this.handleMouseDown},[I(()=>x),u?(p(),i(`div`,{key:0,class:M(`${d}-base-selection__border`)},null,2)):I(()=>null),u?(p(),i(`div`,{key:2,class:M(`${d}-base-selection__state-border`)},null,2)):I(()=>null)],46,Xt)}}),Qt=O([A(`select`,`
 z-index: auto;
 outline: none;
 width: 100%;
 position: relative;
 font-weight: var(--n-font-weight);
 `),A(`select-menu`,`
 margin: 4px 0;
 box-shadow: var(--n-menu-box-shadow);
 `,[De({originalTransition:`background-color .3s var(--n-bezier), box-shadow .3s var(--n-bezier)`})])]),$t=e(e({},L.props),{},{to:Z.propTo,bordered:{type:Boolean,default:void 0},clearable:Boolean,clearCreatedOptionsOnClear:{type:Boolean,default:!0},clearFilterAfterSelect:{type:Boolean,default:!0},options:{type:Array,default:()=>[]},defaultValue:{type:[String,Number,Array],default:null},keyboard:{type:Boolean,default:!0},value:[String,Number,Array],placeholder:String,menuProps:Object,multiple:Boolean,size:String,menuSize:{type:String},filterable:Boolean,disabled:{type:Boolean,default:void 0},remote:Boolean,loading:Boolean,filter:Function,placement:{type:String,default:`bottom-start`},widthMode:{type:String,default:`trigger`},tag:Boolean,onCreate:Function,fallbackOption:{type:[Function,Boolean],default:void 0},show:{type:Boolean,default:void 0},showArrow:{type:Boolean,default:!0},maxTagCount:[Number,String],ellipsisTagPopoverProps:Object,consistentMenuWidth:{type:Boolean,default:!0},virtualScroll:{type:Boolean,default:!0},labelField:{type:String,default:`label`},valueField:{type:String,default:`value`},childrenField:{type:String,default:`children`},renderLabel:Function,renderOption:Function,renderTag:Function,"onUpdate:value":[Function,Array],inputProps:Object,nodeProps:Function,ignoreComposition:{type:Boolean,default:!0},showOnFocus:Boolean,onUpdateValue:[Function,Array],onBlur:[Function,Array],onClear:[Function,Array],onFocus:[Function,Array],onScroll:[Function,Array],onSearch:[Function,Array],onUpdateShow:[Function,Array],"onUpdate:show":[Function,Array],displayDirective:{type:String,default:`show`},resetMenuOnOptionsChange:{type:Boolean,default:!0},status:String,showCheckmark:{type:Boolean,default:!0},scrollbarProps:Object,onChange:[Function,Array],items:Array}),en=t({name:`Select`,props:$t,slots:Object,setup(t){let{mergedClsPrefixRef:n,mergedBorderedRef:r,namespaceRef:i,inlineThemeDisabled:a,mergedComponentPropsRef:o}=te(t),s=L(`Select`,`-select`,Qt,je,t,n),c=S(t.defaultValue),l=y(t,`value`),u=Se(l,c),d=S(!1),p=S(``),m=pe(t,[`items`,`options`]),h=S([]),g=S([]),v=f(()=>g.value.concat(h.value).concat(m.value)),b=f(()=>{let{filter:e}=t;if(e)return e;let{labelField:n,valueField:r}=t;return(e,t)=>{if(!t)return!1;let i=t[n];if(typeof i==`string`)return Bt(e,i);let a=t[r];return typeof a==`string`?Bt(e,a):typeof a==`number`&&Bt(e,String(a))}}),x=f(()=>{if(t.remote)return m.value;{let{value:e}=v,{value:n}=p;return!n.length||!t.filterable?e:Ht(e,b.value,n,t.childrenField)}}),C=f(()=>{let{valueField:e,childrenField:n}=t,r=Vt(e,n);return Ft(x.value,r)}),w=f(()=>Ut(v.value,t.valueField,t.childrenField)),T=S(!1),E=Se(y(t,`show`),T),D=S(null),O=S(null),k=S(null),{localeRef:A}=ue(`Select`),j=f(()=>{var e;return(e=t.placeholder)==null?A.value.placeholder:e}),M=[],N=S(new Map),P=f(()=>{let{fallbackOption:e}=t;if(e===void 0){let{labelField:e,valueField:n}=t;return t=>({[e]:String(t),[n]:t})}return e===!1?!1:t=>Object.assign(e(t),{value:t})});function F(e){let n=t.remote,{value:r}=N,{value:i}=w,{value:a}=P,o=[];return e.forEach(e=>{if(i.has(e))o.push(i.get(e));else if(n&&r.has(e))o.push(r.get(e));else if(a){let t=a(e);t&&o.push(t)}}),o}let I=f(()=>{if(t.multiple){let{value:e}=u;return Array.isArray(e)?F(e):[]}return null}),R=f(()=>{let{value:e}=u;return!t.multiple&&!Array.isArray(e)?e===null?null:F([e])[0]||null:null}),z=ae(t,{mergedSize:e=>{var n;let{size:r}=t;if(r)return r;let{mergedSize:i}=e||{};return i!=null&&i.value?i.value:(o==null||(n=o.value)==null||(n=n.Select)==null?void 0:n.size)||`medium`}}),{mergedSizeRef:B,mergedDisabledRef:V,mergedStatusRef:ne}=z;function H(e,n){let{onChange:r,"onUpdate:value":i,onUpdateValue:a}=t,{nTriggerFormChange:o,nTriggerFormInput:s}=z;r&&G(r,e,n),a&&G(a,e,n),i&&G(i,e,n),c.value=e,o(),s()}function re(e){let{onBlur:n}=t,{nTriggerFormBlur:r}=z;n&&G(n,e),r()}function U(){let{onClear:e}=t;e&&G(e)}function ie(e){let{onFocus:n,showOnFocus:r}=t,{nTriggerFormFocus:i}=z;n&&G(n,e),i(),r&&q()}function W(e){let{onSearch:n}=t;n&&G(n,e)}function oe(e){let{onScroll:n}=t;n&&G(n,e)}function ce(){let{remote:e,multiple:n}=t;if(e){let{value:e}=N;if(n){var r;let{valueField:n}=t;(r=I.value)==null||r.forEach(t=>{e.set(t[n],t)})}else{let n=R.value;n&&e.set(n[t.valueField],n)}}}function le(e){let{onUpdateShow:n,"onUpdate:show":r}=t;n&&G(n,e),r&&G(r,e),T.value=e}function q(){V.value||(le(!0),T.value=!0,t.filterable&&Pe())}function J(){le(!1)}function Y(){p.value=``,g.value=M}let X=S(!1);function de(){t.filterable&&(X.value=!0)}function fe(){t.filterable&&(X.value=!1,E.value||Y())}function me(){V.value||(E.value?t.filterable?Pe():J():q())}function he(e){var t;(t=k.value)!=null&&(t=t.selfRef)!=null&&t.contains(e.relatedTarget)||(d.value=!1,re(e),J())}function ge(e){ie(e),d.value=!0}function _e(){d.value=!0}function ve(e){var t;(t=D.value)!=null&&t.$el.contains(e.relatedTarget)||(d.value=!1,re(e),J())}function ye(){var e;(e=D.value)==null||e.focus(),J()}function be(e){if(E.value){var t;(t=D.value)!=null&&t.$el.contains(se(e))||J()}}function xe(e){if(!Array.isArray(e))return[];if(P.value)return Array.from(e);{let{remote:n}=t,{value:r}=w;if(n){let{value:t}=N;return e.filter(e=>r.has(e)||t.has(e))}return e.filter(e=>r.has(e))}}function Ce(e){we(e.rawNode)}function we(e){if(V.value)return;let{tag:n,remote:r,clearFilterAfterSelect:i,valueField:a}=t;if(n&&!r){let{value:e}=g,t=e[0]||null;if(t){let e=h.value;e.length?e.push(t):h.value=[t],g.value=M}}if(r&&N.value.set(e[a],e),t.multiple){let t=xe(u.value),o=t.findIndex(t=>t===e[a]);if(~o){if(t.splice(o,1),n&&!r){let t=Te(e[a]);~t&&(h.value.splice(t,1),i&&(p.value=``))}}else t.push(e[a]),i&&(p.value=``);H(t,F(t))}else{if(n&&!r){let t=Te(e[a]);~t?h.value=[h.value[t]]:h.value=M}Ne(),J(),H(e[a],e)}}function Te(e){return h.value.findIndex(n=>n[t.valueField]===e)}function Ee(e){E.value||q();let{value:n}=e.target;p.value=n;let{tag:r,remote:i}=t;if(W(n),r&&!i){if(!n){g.value=M;return}let{onCreate:e}=t,r=e?e(n):{[t.labelField]:n,[t.valueField]:n},{valueField:i,labelField:a}=t;m.value.some(e=>e[i]===r[i]||e[a]===r[a])||h.value.some(e=>e[i]===r[i]||e[a]===r[a])?g.value=M:g.value=[r]}}function De(e){e.stopPropagation();let{multiple:n,tag:r,remote:i,clearCreatedOptionsOnClear:a}=t;!n&&t.filterable&&J(),r&&!i&&a&&(h.value=M),U(),n?H([],[]):H(null,null)}function Q(e){!Me(e,`action`)&&!Me(e,`empty`)&&!Me(e,`header`)&&e.preventDefault()}function Oe(e){oe(e)}function Ae(e){if(!t.keyboard){e.preventDefault();return}switch(e.key){case` `:if(t.filterable)break;e.preventDefault();case`Enter`:var n;if(!((n=D.value)!=null&&n.isComposing)){if(E.value){var r;let e=(r=k.value)==null?void 0:r.getPendingTmNode();e?Ce(e):t.filterable||(J(),Ne())}else if(q(),t.tag&&X.value){let e=g.value[0];if(e){let n=e[t.valueField],{value:r}=u;t.multiple&&Array.isArray(r)&&r.includes(n)||we(e)}}}e.preventDefault();break;case`ArrowUp`:var i;if(e.preventDefault(),t.loading)return;E.value&&((i=k.value)==null||i.prev());break;case`ArrowDown`:var a;if(e.preventDefault(),t.loading)return;E.value?(a=k.value)==null||a.next():q();break;case`Escape`:var o;E.value&&(ke(e),J()),(o=D.value)==null||o.focus()}}function Ne(){var e;(e=D.value)==null||e.focus()}function Pe(){var e;(e=D.value)==null||e.focusInput()}function Fe(){var e;E.value&&((e=O.value)==null||e.syncPosition())}ce(),_(y(t,`options`),ce);let Ie={focus:()=>{var e;(e=D.value)==null||e.focus()},focusInput:()=>{var e;(e=D.value)==null||e.focusInput()},blur:()=>{var e;(e=D.value)==null||e.blur()},blurInput:()=>{var e;(e=D.value)==null||e.blurInput()}},Le=f(()=>{let{self:{menuBoxShadow:e}}=s.value;return{"--n-menu-box-shadow":e}}),Re=a?ee(`select`,void 0,Le,t):void 0;return e(e({},Ie),{},{mergedStatus:ne,mergedClsPrefix:n,mergedBordered:r,namespace:i,treeMate:C,isMounted:K(),triggerRef:D,menuRef:k,pattern:p,uncontrolledShow:T,mergedShow:E,adjustedTo:Z(t),uncontrolledValue:c,mergedValue:u,followerRef:O,localizedPlaceholder:j,selectedOption:R,selectedOptions:I,mergedSize:B,mergedDisabled:V,focused:d,activeWithoutMenuOpen:X,inlineThemeDisabled:a,onTriggerInputFocus:de,onTriggerInputBlur:fe,handleTriggerOrMenuResize:Fe,handleMenuFocus:_e,handleMenuBlur:ve,handleMenuTabOut:ye,handleTriggerClick:me,handleToggle:Ce,handleDeleteOption:we,handlePatternInput:Ee,handleClear:De,handleTriggerBlur:he,handleTriggerFocus:ge,handleKeydown:Ae,handleMenuAfterLeave:Y,handleMenuClickOutside:be,handleMenuScroll:Oe,handleMenuKeydown:Ae,handleMenuMousedown:Q,mergedTheme:s,cssVars:a?void 0:Le,themeClass:Re==null?void 0:Re.themeClass,onRender:Re==null?void 0:Re.onRender})},render(){return p(),i(`div`,{class:M(`${this.mergedClsPrefix}-select`)},[b(fe,null,{_:1,default:P(()=>[(p(),T(ye,null,{_:1,default:P(()=>(p(),T(Zt,{ref:`triggerRef`,inlineThemeDisabled:this.inlineThemeDisabled,status:this.mergedStatus,inputProps:this.inputProps,clsPrefix:this.mergedClsPrefix,showArrow:this.showArrow,maxTagCount:this.maxTagCount,ellipsisTagPopoverProps:this.ellipsisTagPopoverProps,bordered:this.mergedBordered,active:this.activeWithoutMenuOpen||this.mergedShow,pattern:this.pattern,placeholder:this.localizedPlaceholder,selectedOption:this.selectedOption,selectedOptions:this.selectedOptions,multiple:this.multiple,renderTag:this.renderTag,renderLabel:this.renderLabel,filterable:this.filterable,clearable:this.clearable,disabled:this.mergedDisabled,size:this.mergedSize,theme:this.mergedTheme.peers.InternalSelection,labelField:this.labelField,valueField:this.valueField,themeOverrides:this.mergedTheme.peerOverrides.InternalSelection,loading:this.loading,focused:this.focused,onClick:this.handleTriggerClick,onDeleteOption:this.handleDeleteOption,onPatternInput:this.handlePatternInput,onClear:this.handleClear,onBlur:this.handleTriggerBlur,onFocus:this.handleTriggerFocus,onKeydown:this.handleKeydown,onPatternBlur:this.onTriggerInputBlur,onPatternFocus:this.onTriggerInputFocus,onResize:this.handleTriggerOrMenuResize,ignoreComposition:this.ignoreComposition},{_:1,arrow:P(()=>{var e,t;return[(e=(t=this.$slots).arrow)==null?void 0:e.call(t)]})},8,`inlineThemeDisabled.status.inputProps.clsPrefix.showArrow.maxTagCount.ellipsisTagPopoverProps.bordered.active.pattern.placeholder.selectedOption.selectedOptions.multiple.renderTag.renderLabel.filterable.clearable.disabled.size.theme.labelField.valueField.themeOverrides.loading.focused.onClick.onDeleteOption.onPatternInput.onClear.onBlur.onFocus.onKeydown.onPatternBlur.onPatternFocus.onResize.ignoreComposition`.split(`.`))))})),(p(),T(he,{ref:`followerRef`,show:this.mergedShow,to:this.adjustedTo,teleportDisabled:this.adjustedTo===Z.tdkey,containerClass:this.namespace,width:this.consistentMenuWidth?`target`:void 0,minWidth:`target`,placement:this.placement},{_:1,default:P(()=>(p(),T(v,{name:`fade-in-scale-up-transition`,appear:this.isMounted,onAfterLeave:this.handleMenuAfterLeave},{_:1,default:P(()=>{var e,t,n;return this.mergedShow||this.displayDirective===`show`?((e=this.onRender)==null||e.call(this),d((p(),T(Lt,a(this.menuProps,{ref:`menuRef`,onResize:this.handleTriggerOrMenuResize,inlineThemeDisabled:this.inlineThemeDisabled,virtualScroll:this.consistentMenuWidth&&this.virtualScroll,class:[`${this.mergedClsPrefix}-select-menu`,this.themeClass,(t=this.menuProps)==null?void 0:t.class],clsPrefix:this.mergedClsPrefix,focusable:!0,labelField:this.labelField,valueField:this.valueField,autoPending:!0,nodeProps:this.nodeProps,theme:this.mergedTheme.peers.InternalSelectMenu,themeOverrides:this.mergedTheme.peerOverrides.InternalSelectMenu,treeMate:this.treeMate,multiple:this.multiple,size:this.menuSize,renderOption:this.renderOption,renderLabel:this.renderLabel,value:this.mergedValue,style:[(n=this.menuProps)==null?void 0:n.style,this.cssVars],onToggle:this.handleToggle,onScroll:this.handleMenuScroll,onFocus:this.handleMenuFocus,onBlur:this.handleMenuBlur,onKeydown:this.handleMenuKeydown,onTabOut:this.handleMenuTabOut,onMousedown:this.handleMenuMousedown,show:this.mergedShow,showCheckmark:this.showCheckmark,resetMenuOnOptionsChange:this.resetMenuOnOptionsChange,scrollbarProps:this.scrollbarProps}),{_:1,empty:P(()=>{var e,t;return[(e=(t=this.$slots).empty)==null?void 0:e.call(t)]}),header:P(()=>{var e,t;return[(e=(t=this.$slots).header)==null?void 0:e.call(t)]}),action:P(()=>{var e,t;return[(e=(t=this.$slots).action)==null?void 0:e.call(t)]})},16,`onResize.inlineThemeDisabled.virtualScroll.class.clsPrefix.labelField.valueField.nodeProps.theme.themeOverrides.treeMate.multiple.size.renderOption.renderLabel.value.style.onToggle.onScroll.onFocus.onBlur.onKeydown.onTabOut.onMousedown.show.showCheckmark.resetMenuOnOptionsChange.scrollbarProps`.split(`.`))),this.displayDirective===`show`?[[x,this.mergedShow],[le,this.handleMenuClickOutside,void 0,{capture:!0}]]:[[le,this.handleMenuClickOutside,void 0,{capture:!0}]])):null})},8,[`appear`,`onAfterLeave`])))},8,[`show`,`to`,`teleportDisabled`,`containerClass`,`width`,`placement`]))])})],2)}}),tn=O([O(`@keyframes spin-rotate`,`
 from {
 transform: rotate(0);
 }
 to {
 transform: rotate(360deg);
 }
 `),A(`spin-container`,`
 position: relative;
 `,[A(`spin-body`,`
 position: absolute;
 top: 50%;
 left: 50%;
 transform: translateX(-50%) translateY(-50%);
 `,[ne()])]),A(`spin-body`,`
 display: inline-flex;
 align-items: center;
 justify-content: center;
 flex-direction: column;
 `),A(`spin`,`
 display: inline-flex;
 height: var(--n-size);
 width: var(--n-size);
 font-size: var(--n-size);
 color: var(--n-color);
 `,[k(`rotate`,`
 animation: spin-rotate 2s linear infinite;
 `)]),A(`spin-description`,`
 display: inline-block;
 font-size: var(--n-font-size);
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 margin-top: 8px;
 `),A(`spin-content`,`
 opacity: 1;
 transition: opacity .3s var(--n-bezier);
 pointer-events: all;
 `,[k(`spinning`,`
 user-select: none;
 -webkit-user-select: none;
 pointer-events: none;
 opacity: var(--n-opacity-spinning);
 `)])]),nn={small:20,medium:18,large:16},rn=e(e(e({},L.props),{},{contentClass:String,contentStyle:[Object,String],description:String,size:{type:[String,Number],default:`medium`},show:{type:Boolean,default:!0},rotate:{type:Boolean,default:!0},spinning:{type:Boolean,validator:()=>!0,default:void 0},delay:Number},J),{},{strokeWidth:Number}),an=t({name:`Spin`,props:rn,slots:Object,setup(e){let{mergedClsPrefixRef:t,inlineThemeDisabled:n}=te(e),r=L(`Spin`,`-spin`,tn,Ae,e,t),i=f(()=>{let{size:t}=e,{common:{cubicBezierEaseInOut:n},self:i}=r.value,{opacitySpinning:a,color:o,textColor:s}=i;return{"--n-bezier":n,"--n-opacity-spinning":a,"--n-size":typeof t==`number`?X(t):i[N(`size`,t)],"--n-color":o,"--n-text-color":s}}),a=n?ee(`spin`,f(()=>{let{size:t}=e;return typeof t==`number`?String(t):t[0]}),i,e):void 0,o=pe(e,[`spinning`,`show`]),s=S(!1);return g(t=>{let n;if(o.value){let{delay:r}=e;if(r){n=window.setTimeout(()=>{s.value=!0},r),t(()=>{clearTimeout(n)});return}}s.value=o.value}),{mergedClsPrefix:t,active:s,mergedStrokeWidth:f(()=>{let{strokeWidth:t}=e;if(t!==void 0)return t;let{size:n}=e;return nn[typeof n==`number`?`medium`:n]}),cssVars:n?void 0:i,themeClass:a==null?void 0:a.themeClass,onRender:a==null?void 0:a.onRender}},render(){var e;let{$slots:t,mergedClsPrefix:n,description:a}=this,o=t.icon&&this.rotate,s=(a||t.description)&&(p(),i(`div`,{class:M(`${n}-spin-description`)},[I(()=>{var e;return a||((e=t.description)==null?void 0:e.call(t))})],2)),c=t.icon?(p(),i(`div`,{key:1,class:M([`${n}-spin-body`,this.themeClass])},[r(`div`,{class:M([`${n}-spin`,o&&`${n}-spin--rotate`]),style:C(t.default?``:this.cssVars)},[I(()=>t.icon())],6),I(()=>s)],2)):(p(),i(`div`,{key:2,class:M([`${n}-spin-body`,this.themeClass])},[(p(),T(ce,{clsPrefix:n,style:C(t.default?``:this.cssVars),stroke:this.stroke,"stroke-width":this.mergedStrokeWidth,radius:this.radius,scale:this.scale,class:M(`${n}-spin`)},null,8,[`clsPrefix`,`style`,`stroke`,`stroke-width`,`radius`,`scale`,`class`])),I(()=>s)],2));return(e=this.onRender)==null||e.call(this),t.default?(p(),i(`div`,{key:3,class:M([`${n}-spin-container`,this.themeClass]),style:C(this.cssVars)},[r(`div`,{class:M([`${n}-spin-content`,this.active&&`${n}-spin-content--spinning`,this.contentClass]),style:C(this.contentStyle)},[I(()=>{var e;return(e=t.default)==null?void 0:e.call(t)})],6),b(v,{name:`fade-in-transition`},{default:()=>this.active?c:null},1024)],6)):c}});export{Ft as a,Ue as c,Lt as i,Me as l,en as n,Mt as o,Vt as r,_t as s,an as t};