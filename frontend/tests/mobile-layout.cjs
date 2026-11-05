/* Rendu mobile réel : largeur, carrousel, navigation et marque. */
const {chromium}=require('playwright-core');const assert=require('node:assert/strict');const fs=require('node:fs');
require('../dist/journey-model.js');const docs=globalThis.CreditModel.suggestedDocuments;
assert(docs('individuals','employee').includes('employment_certificate'));
assert(!docs('individuals','retired').includes('employment_certificate'));
assert(!docs('businesses').includes('employment_certificate'));
(async()=>{const base=process.env.CREDIT_E2E_URL;if(!base)throw Error('Définir CREDIT_E2E_URL');const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});let count=3;
try{for(const width of [320,360,390,414,768]){const page=await browser.newPage({viewport:{width,height:844},isMobile:true,hasTouch:true});await page.goto(base+'/#overview');await page.waitForSelector('.stories');
assert((await page.title()).includes('Crédix'));count++;
for(const stage of ['initial','carousel','navigation']){
if(stage==='carousel')await page.locator('.stories').evaluate(el=>{el.scrollLeft=el.scrollWidth});
if(stage==='navigation'){await page.locator('.nav-scroll').evaluate(el=>{el.scrollLeft=el.scrollWidth});await page.evaluate(()=>window.scrollTo({left:999,top:0}));}
await page.waitForTimeout(150);const dimensions=await page.evaluate(()=>({inner:innerWidth,width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,x:scrollX}));assert.equal(dimensions.inner,width,JSON.stringify(dimensions));assert(dimensions.scroll<=width+1,JSON.stringify(dimensions));assert.equal(dimensions.x,0);count+=3;
}
await page.locator('.stories').evaluate(el=>{el.scrollLeft=0});
await page.evaluate(()=>window.scrollTo(0,0));if(width===320&&process.env.CREDIT_E2E_OUTPUT){fs.mkdirSync(process.env.CREDIT_E2E_OUTPUT,{recursive:true});await page.screenshot({path:process.env.CREDIT_E2E_OUTPUT+'/credix-mobile-320.png',fullPage:true});}
await page.close();}console.log(count+' contrôles marque, documents et mobile réussis.');}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
