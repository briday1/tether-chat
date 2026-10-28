import test from 'node:test';import assert from 'node:assert/strict';
import {DriveFiles} from '../../tether/drive-sync-service.mjs';
const session={mode:'folder-records',folderId:'folder12345',workspaceId:'folder12345'};
const op={version:1,id:'operation_001',actor:'device_0001',when:'2026-10-28T00:00:00Z',changes:[{key:'task:task1',field:'$exists',value:false,parents:[]}]};
test('Drive journal reads are folder-bound, cached and never send token in URL',async()=>{
 const calls=[];const drive=new DriveFiles(async(url,options)=>{calls.push([url,options]);assert.ok(!url.includes('secret-token'));assert.equal(options.headers.Authorization,'Bearer secret-token');
  return Response.json(url.includes('alt=media')?{workspace:session.workspaceId,operation:op}:{files:[{id:'file123456',name:'tether-change-operation_001.json',size:100,modifiedTime:'1',md5Checksum:'a'}]})});
 assert.deepEqual(await drive.pull('secret-token',session),[op]);assert.deepEqual(await drive.pull('secret-token',session),[op]);assert.equal(calls.filter(([url])=>url.includes('alt=media')).length,1);assert.ok(decodeURIComponent(calls[0][0]).includes('folder12345'));assert.equal(calls[0][1].credentials,'omit');assert.equal(calls[0][1].redirect,'error');
});
test('stopping sync prevents remaining uploads and replay uses immutable operation ID',async()=>{
 let active=true;const calls=[];const drive=new DriveFiles(async(url,options)=>{calls.push([url,options]);active=false;return Response.json({id:'created_file'})});
 await assert.rejects(drive.push('token',session,[op,{...op,id:'operation_002'}],op.actor,[],{isActive:()=>active}),/stopped/);assert.equal(calls.length,1);assert.ok(calls[0][1].body.includes('tether-change-operation_001.json'));assert.ok(!calls[0][1].body.includes('token'));
});
test('auth failures and corrupt file history fail closed',async()=>{
 const denied=new DriveFiles(async()=>new Response('{}',{status:401}));await assert.rejects(denied.pull('token',session),error=>error.status===401);
 const corrupt=new DriveFiles(async url=>Response.json(url.includes('alt=media')?{workspace:session.workspaceId,operation:{...op,version:999}}:{files:[{id:'f',name:'tether-change-operation_001.json',size:10}]}));await assert.rejects(corrupt.pull('token',session),/Invalid/);
});
