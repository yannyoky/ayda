# kotlinx.serialization keeps generated serializers via its own consumer rules.
# Ktor references optional classes that are absent on Android.
-dontwarn org.slf4j.**
