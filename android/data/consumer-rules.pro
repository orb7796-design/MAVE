# Gson models are read by reflection; keep them (and their generic signatures) in any app that uses this module.
-keepattributes Signature, *Annotation*, InnerClasses, EnclosingMethod
-keep class com.mave.app.data.** { *; }
