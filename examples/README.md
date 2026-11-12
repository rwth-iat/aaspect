# Demo file

`demo.aasx` is one invented AAS package that gives every analysis something to report.
It names no real manufacturer or product. Run it with **Run the demo** on the start page,
or download it from there, and wait for the analysis to finish (a few seconds). It ships
with the app as `src/aaspect/adapters/web/static/demo.aasx`.

It is written by `tools/demo_file.py`; change the script, not the package, and run

```bash
uv run python tools/demo_file.py
```

The package holds three AAS parts, which the report treats as three documents:

| Part | Content |
|---|---|
| `demo-pump.json` | Shell `DemoPump` (instance) with a Digital Nameplate 3.0, an operating data submodel holding every element type, a deprecated ZVEI nameplate and a concept description |
| `demo-pump-type.json` | Shell `DemoPumpType` (type), repeating the concept description identically, the ZVEI nameplate's id with other content, and the concept description's IRDI in lower case |
| `broken.json` | Cut off after its first characters |

Two embedded files, `logo.png` (also the thumbnail) and `manual.pdf`, are referenced from
File elements.

## What the report shows

**Schema check.** Two documents of version 3.0, one valid. The first violates the
idShort pattern (`2ndStage`) and the minimum length of a description text; the third is
not well-formed JSON.

**Graph import.** Two documents imported, one not. The concept description repeated
identically counts once. The ZVEI nameplate id carries two different contents, reported
as an id collision.

**Metamodel constraints.**

| Constraint | Where |
|---|---|
| AASd-002 | idShort `2ndStage` |
| AASd-005 | `OperatingData` has a revision but no version |
| AASd-014 | Entity `Impeller` is self-managed without an asset id |
| AASd-022 | `Temperature` twice in `OperatingData` |
| AASd-077 | Extension `source` twice on `OperatingData` |
| AASd-107 | List `Readings`: items' semanticId differs from `semanticIdListElement` |
| AASd-109 | List `Readings`: an item of another valueType |
| AASd-118 | `Untyped` has supplementalSemanticIds but no semanticId |
| AASd-120 | List `Readings`: an item with an idShort |
| AASd-127 | `NameplateLink` has a FragmentReference after a Submodel key |
| AASd-129 | `Speed` carries a TemplateQualifier in an instance |
| AASd-133 | specificAssetId `PartNumber` has a ModelReference as externalSubjectId |
| AASd-134 | Operation `Reset` uses `Mode` as input and output |

**Analytics.** Every SubmodelElement type, seven valueTypes, nesting four levels deep,
semanticIds as IRDI (ECLASS, IEC CDD), IRI, URN and UUID, supplementalSemanticIds,
descriptions in two languages, displayNames, an invalid language tag (`english`), both
assetKinds and two specificAssetId names.

**Submodel template conformance.** One deviation of every kind on the Digital Nameplate
3.0:

| Kind | Where |
|---|---|
| Missing | `OrderCodeOfManufacturer` |
| Cardinality | `ManufacturerProductDesignation` twice |
| Model type | `ManufacturerProductFamily` as a Property |
| Value type | `DateOfManufacture` as `xs:string` |
| semanticId version | `ManufacturerName` with IRDI version `#008` |
| idShort | `SerialNo` for `SerialNumber` |
| Not in template | `InternalNote` |

The ZVEI nameplate is matched to its deprecated edition, and `OperatingData` has no
template.

**Lint.** One case of every check:

| Check | Where |
|---|---|
| LINT-WS-ID | specificAssetId `SerialNumber` of `DemoPumpType` ends in a space |
| LINT-WS-TEXT | qualifier type `Unit ` on `Speed` |
| LINT-ID-FORM | `Pressure`'s semanticId, an IRDI without its version |
| LINT-ID-TEMPLATE | the ZVEI nameplate keeps its template's submodel id (both parts) |
| LINT-ID-EXAMPLE | every shell, submodel and asset id: the demo lives on `example.com` |
| LINT-ID-NEAR | the concept description `0173-1#02-aao677#002` in lower case |
| LINT-ID-ASSET | `DemoPumpType`'s globalAssetId is its own shell id |
| LINT-DEP-CATEGORY | `FlowRate` has a category |
| LINT-DEP-QUALIFIER | `Running` has a `Multiplicity` qualifier |
| LINT-TPL-QUALIFIER | `Running` has an `SMT/Cardinality` qualifier in an instance |
| LINT-REF-DANGLING | `SpareLink` names `SparePart`, which `OperatingData` lacks |

## Not covered by one file

- **Uploaded templates** come in a second upload field. A template for `OperatingData`
  needs a submodel of kind `Template` with semanticId
  `urn:example:submodel:operating-data:1:0`.
- **Mixed metamodel versions:** all parts are 3.0, so no file is named as checked by
  another version than its own.
