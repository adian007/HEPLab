"""Run with cmsRun inside CMSSW_10_6_30, not ordinary Python.

Ideal Extended2016 DDD -> ROOT TGeo solids/materials, using the upstream
Fireworks exporter at depth 100. Not the aligned reconstruction geometry or
an IOV-resolved material measurement. Completeness must be checked from logs.
"""
import FWCore.ParameterSet.Config as cms

process = cms.Process("HEPLABGEOMETRY")
process.load("Geometry.CMSCommonData.cmsExtendedGeometry2016XML_cfi")
process.source = cms.Source("EmptySource")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(1))
process.add_(cms.ESProducer("TGeoMgrFromDdd",
                           verbose=cms.untracked.bool(True), level=cms.untracked.int32(100)))
process.dump = cms.EDAnalyzer("DumpSimGeometry",
                             tag=cms.untracked.string("HEPLab-ideal-Extended2016-depth100"),
                             outputFileName=cms.untracked.string("cms-ideal-2016.root"))
process.p = cms.Path(process.dump)
