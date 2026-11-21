const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

async function app({supported=true,permission='default'}={}) {
    const clicks={}, messages=[], saved={};
    let requests=0;
    const buttons=Object.fromEntries(['install-app-btn','enable-alerts-btn','app-status','offline-status'].map(id=>[id,{
        setAttribute(){},addEventListener(event,fn){clicks[id]=fn;}
    }]));
    const registration={showNotification:async(title,options)=>messages.push({title,...options})};
    const snapshot={latest_observation_date:'2026-11-20',anomalies:[{id:'KAK|2026-11-20',station:'KAK'}]};
    const notifications={permission,requestPermission:async()=>{requests++;notifications.permission='granted';return 'granted';}};
    const window={isSecureContext:true,matchMedia:()=>({matches:false}),addEventListener(){}};
    if(supported) window.Notification=notifications;
    const context=vm.createContext({window, Notification:notifications, URL, Set,
        document:{baseURI:'https://example.com/project/',readyState:'complete',body:{classList:{toggle(){}}},
            getElementById:id=>buttons[id],addEventListener(){}},
        navigator:{onLine:true,serviceWorker:{register:async()=>registration,ready:Promise.resolve(registration),addEventListener(){}}},
        localStorage:{getItem:()=>null,setItem:(key,value)=>saved[key]=value},setInterval(){},
        fetch:async()=>({ok:true,headers:{get:()=>snapshot.cached?'1':null},json:async()=>snapshot})});
    vm.runInContext(fs.readFileSync(require.resolve('../static/pwa.js'),'utf8'),context);
    await new Promise(resolve=>setImmediate(resolve));
    return {buttons,clicks,messages,snapshot,requests:()=>requests,check:()=>window.GempraApp.checkAlerts()};
}

test('alerts require a gesture and baseline; fresh records notify once, cached records never notify',async()=>{
    const page=await app();
    assert.equal(page.requests(),0);
    assert.equal(page.messages.length,0);
    await page.clicks['enable-alerts-btn']();
    assert.equal(page.requests(),1);
    assert.equal(page.messages.length,0);
    page.snapshot.latest_observation_date='2026-11-21';
    page.snapshot.anomalies=[{id:'KAK|2026-11-21',station:'KAK'}];
    await page.check(); await page.check();
    assert.equal(page.messages.length,1);
    page.snapshot.anomalies.push({id:'NGK|2026-11-21',station:'NGK'});
    await page.check();
    assert.equal(page.messages.length,2);
    page.snapshot.latest_observation_date='2026-11-22';page.snapshot.cached=true;
    await page.check();assert.equal(page.messages.length,2);
    assert.equal(page.buttons['offline-status'].hidden,false);
    await page.clicks['enable-alerts-btn']();
    page.snapshot.cached=false;await page.check();assert.equal(page.messages.length,2);
});

test('unsupported and denied browsers show meaningful states without a permission prompt',async()=>{
    const unsupported=await app({supported:false});
    assert.equal(unsupported.buttons['enable-alerts-btn'].disabled,true);
    assert.equal(unsupported.buttons['enable-alerts-btn'].textContent,'Alerts unavailable');
    const denied=await app({permission:'denied'});
    await denied.clicks['enable-alerts-btn']();
    assert.match(denied.buttons['app-status'].textContent,/blocked/);
    assert.equal(denied.requests(),0);
});
