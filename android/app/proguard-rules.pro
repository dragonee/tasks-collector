# Keep generated Kotlinx Serialization companions
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt

-keep,includedescriptorclasses class com.dragonee.tasks.health.**$$serializer { *; }
-keepclassmembers class com.dragonee.tasks.health.** {
    *** Companion;
}
-keepclasseswithmembers class com.dragonee.tasks.health.** {
    kotlinx.serialization.KSerializer serializer(...);
}
