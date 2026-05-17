# Keep generated Kotlinx Serialization companions
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt

-keep,includedescriptorclasses class org.polybrain.tasks.health.**$$serializer { *; }
-keepclassmembers class org.polybrain.tasks.health.** {
    *** Companion;
}
-keepclasseswithmembers class org.polybrain.tasks.health.** {
    kotlinx.serialization.KSerializer serializer(...);
}
