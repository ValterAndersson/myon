// Script to manually update timezone for production user
// Run this in Firebase Console -> Firestore -> Data -> Run query

// Update user timezone to Helsinki
const userId = "YOUR_USER_ID"; // Replace with actual user ID
const userRef = db.collection('users').doc(userId);

userRef.update({
  timezone: "Europe/Helsinki",
  updated_at: admin.firestore.FieldValue.serverTimestamp()
}).then(() => {
  console.log("Timezone updated to Helsinki for user:", userId);
}).catch((error) => {
  console.error("Error updating timezone:", error);
});
